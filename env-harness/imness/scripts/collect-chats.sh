#!/bin/bash
# collect-chats.sh — 飞书会话采集 → knowledge/raw/transcripts/（bold-speaker 格式，已打码）
#
# 多实例控制流（#25 落地，#22/#23/#24 决策）：
#   遍历所有飞书实例 → 每个实例切对应 lark profile → 遍历该实例 project_tags
#   → 列会话 → 拉消息 → 归一化（含 redact 打码 + source_channel/source_instance
#   frontmatter）→ 与已有 raw 文件去重合并 → 写 raw/transcripts
#
# 入口：
#   collect-chats.sh                    # 遍历 config 所有飞书实例
#   collect-chats.sh --instance <name>  # 只采某实例
#   collect-chats.sh --all              # 遍历所有实例（同无参，向后兼容）
#   collect-chats.sh --feed-id <chat_id> # 只采指定会话（用首个实例的 profile）
#   collect-chats.sh --dry-run          # 只打印控制流，不调 lark-cli 采集
#
# 详见 imness/SKILL.md collect-chats 段落。
set -eo pipefail
source "$(dirname "$0")/common.sh"

TRANSCRIPTS_DIR="$KNOWLEDGE_DIR/raw/transcripts"
INDEX_FILE="$KNOWLEDGE_DIR/index.json"
LOG_FILE="$KNOWLEDGE_DIR/sync.log"
TOOLS="$TOOLS_PY"

# 文件切割阈值（KB），超过此值自动冻结当前文件、新建当月文件（Ticket 02）
SPLIT_SIZE_KB=${SPLIT_SIZE_KB:-200}

TARGET_FEED_ID="" ALL=0 DRY_RUN=0 TARGET_INSTANCE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --feed-id) TARGET_FEED_ID="$2"; shift 2 ;;
    --all) ALL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --instance) TARGET_INSTANCE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

mkdir -p "$TRANSCRIPTS_DIR"
chmod +x "$TOOLS"

# === 函数 ===

get_active_file() {
  # $1=file_prefix（{safe_name}_{feed_id前12位}）
  # stdout = 当前活跃文件名（不含路径）。无历史文件时生成新命名（_{YYYY-MM}.md）。
  local prefix="$1"
  local existing; existing=$(python3 "$TOOLS" cmd_find_active "$TRANSCRIPTS_DIR" "$prefix" 2>/dev/null || echo "")
  if [[ -n "$existing" ]]; then
    echo "$existing"
  else
    local month; month=$(date +%Y-%m)
    echo "${prefix}_${month}.md"
  fi
}

get_chat_list() {
  local group_id="$1"
  info "读取标签会话列表 (group_id=$group_id)..."
  lark-cli im +feed-group-list-item --feed-group-id "$group_id" --page-all --format json 2>/dev/null
}

detect_display_name() {
  local feed_id="$1" chat_name="$2" instance="$3"
  if [[ -n "$chat_name" ]]; then echo "$chat_name"; return; fi
  info "  辨认 display_name..."
  local -a flags=(cmd_find_name $(instance_flag "$instance"))
  lark-cli im +chat-messages-list --chat-id "$feed_id" --page-size 10 --order desc --format json 2>/dev/null \
    | python3 "$TOOLS" "${flags[@]}" 2>/dev/null || echo "未知_${feed_id:0:12}"
}

pull_messages() {
  local feed_id="$1" start_time="$2"
  local page_token="" all_msgs="[]"
  while true; do
    # --order asc：消息按时间正序（旧→新，符合 timeline 阅读习惯，spec US 10）
    local -a flags=(--chat-id "$feed_id" --page-size 50 --order asc --format json)
    [[ -n "$start_time" ]] && flags+=(--start "$start_time")
    [[ -n "$page_token" ]] && flags+=(--page-token "$page_token")
    local out
    out=$(lark-cli im +chat-messages-list "${flags[@]}" 2>/dev/null) || { warn "拉取失败"; break; }
    local has_more; has_more=$(echo "$out" | python3 "$TOOLS" cmd_has_more 2>/dev/null || echo "False")
    local pt; pt=$(echo "$out" | python3 "$TOOLS" cmd_page_token 2>/dev/null || echo "")
    local new_msgs; new_msgs=$(echo "$out" | python3 "$TOOLS" cmd_pull 2>/dev/null || echo "[]")
    all_msgs=$(printf '%s\n%s\n' "$all_msgs" "$new_msgs" | python3 "$TOOLS" cmd_merge 2>/dev/null || echo "[]")
    page_token="$pt"
    [[ "$has_more" == "True" ]] || break
  done
  echo "$all_msgs"
}

process_chat() {
  # $1=feed_id $2=chat_name $3=feed_type $4=instance $5=group_id
  local feed_id="$1" chat_name="$2" feed_type="$3" instance="$4" group_id="$5"
  local start_ts; start_ts=$(date +%s)

  local display_name; display_name=$(detect_display_name "$feed_id" "$chat_name" "$instance")
  info "处理: $display_name ($feed_id)"

  local safe_name; safe_name=$(sanitize_filename "$display_name")
  local file_prefix="${safe_name}_${feed_id:0:12}"
  local file_name; file_name=$(get_active_file "$file_prefix")
  local file_path="$TRANSCRIPTS_DIR/$file_name"

  # 读增量游标（按 instance 隔离），schema 知识收拢在 cmd_get_cursor
  local cursor prev_count last_ct
  local -a cursor_flags=(cmd_get_cursor "$INDEX_FILE" "$feed_id" $(instance_flag "$instance"))
  if [[ -f "$INDEX_FILE" ]]; then
    cursor=$(python3 "$TOOLS" "${cursor_flags[@]}" 2>/dev/null || echo "0 ")
    prev_count=$(echo "$cursor" | cut -d' ' -f1)
    last_ct=$(echo "$cursor" | cut -d' ' -f2-)
  else
    prev_count=0 last_ct=""
  fi

  local mode="首次全量" start_flag=""
  if [[ "$prev_count" -gt 0 && -n "$last_ct" ]]; then
    mode="增量"
    start_flag="$last_ct"
    info "  增量模式 (已有 $prev_count 条, 游标 $last_ct)"
  fi

  local msgs; msgs=$(pull_messages "$feed_id" "$start_flag")

  # 归一化（cmd_normalize 内部已调 redact 打码；--instance 写 source frontmatter）
  local tmp_new; tmp_new=$(mktemp)
  local -a norm_flags=(cmd_normalize $(instance_flag "$instance"))
  echo "$msgs" | python3 "$TOOLS" "${norm_flags[@]}" 2>/dev/null > "$tmp_new"
  local new_count last_create_time
  new_count=$(grep 'MESSAGE_COUNT:' "$tmp_new" | tail -1 | sed 's/MESSAGE_COUNT://' || echo 0)
  last_create_time=$(grep 'LAST_CREATE_TIME:' "$tmp_new" | tail -1 | sed 's/LAST_CREATE_TIME://' || echo "")
  # 去掉计数行（保留正文）
  sed -i '' '/MESSAGE_COUNT:/d;/LAST_CREATE_TIME:/d' "$tmp_new" 2>/dev/null || sed -i '/MESSAGE_COUNT:/d;/LAST_CREATE_TIME:/d' "$tmp_new"

  # 按 msg_id 去重合并：已有文件 + 新内容 → 重写文件（幂等）
  # frontmatter 由 cmd_dedupe_merge 在合并时保留（#25 修复增量丢失）
  local final_count
  if [[ -f "$file_path" ]]; then
    python3 "$TOOLS" cmd_dedupe_merge "$tmp_new" < "$file_path" > "$file_path.new" 2>/dev/null
    mv "$file_path.new" "$file_path"
    # 计数口径统一：基于文件内 msg_id 锚点数（与 cmd_normalize 的 seen 口径一致）
    final_count=$(grep -c 'msg_id:' "$file_path" 2>/dev/null || echo 0)
  else
    cp "$tmp_new" "$file_path"
    final_count="$new_count"
  fi
  rm -f "$tmp_new"

  # 超阈值自动切割：冻结当前文件，新建当月文件承接后续消息
  # 文件大小 > SPLIT_SIZE_KB 且当前文件未以当月后缀结尾时触发
  local cur_month; cur_month=$(date +%Y-%m)
  local size_kb; size_kb=$(du -k "$file_path" 2>/dev/null | cut -f1 || echo 0)
  if [[ "$size_kb" -gt "$SPLIT_SIZE_KB" && "$file_name" != *"_${cur_month}.md" ]]; then
    local new_name="${file_prefix}_${cur_month}.md"
    # 检查新文件名是否已存在（同月重复切的极端情况，跳过）
    if [[ ! -f "$TRANSCRIPTS_DIR/$new_name" ]]; then
      touch "$TRANSCRIPTS_DIR/$new_name"
      echo "$(date +%Y-%m-%dT%H:%M:%S+08:00) | [$instance] SPLIT | $display_name: ${size_kb}KB → $new_name" >> "$LOG_FILE"
      ok "  切割: ${size_kb}KB → $new_name (下次采集自动切换)"
    fi
  fi

  # 写入游标（last_create_time 为本次拉取的最大时间，作下次增量起点）
  local -a idx_flags=(cmd_update_index "$feed_id" "$display_name" "$feed_type" \
    "raw/transcripts/$file_name" "$final_count" "$INDEX_FILE" "$group_id" "$last_create_time" $(instance_flag "$instance"))
  python3 "$TOOLS" "${idx_flags[@]}"

  local d; d=$(($(date +%s) - start_ts))
  local new_added=$(( final_count - prev_count ))
  [[ "$new_added" -lt 0 ]] && new_added=0
  echo "$(date +%Y-%m-%dT%H:%M:%S+08:00) | [$instance] $display_name | $mode | +${new_added} (总$final_count) | ${d}s" >> "$LOG_FILE"
  ok "  $display_name: $mode, 总$final_count 条 (+${new_added}), ${d}s"
}

collect_for_instance() {
  local instance="$1" lark_profile="$2"
  info "=== 实例: $instance (profile=$lark_profile) ==="

  # 切到该实例的 profile（串行采集，全局 profile 状态）
  if [[ "$DRY_RUN" -eq 0 ]]; then
    info "切换 profile → $lark_profile"
    lark-cli profile use "$lark_profile" >/dev/null 2>&1 || warn "profile 切换失败（继续用当前）"
  else
    info "[dry-run] 将切换 profile → $lark_profile"
  fi

  # 取该实例的 project_tags（#22：匹配这些标签的群才采）
  local tags_json
  tags_json=$(python3 "$SCRIPT_DIR/config.py" instance "$instance" --field project_tags 2>/dev/null)
  local tags=()
  while IFS= read -r t; do tags+=("$t"); done < <(python3 -c "import ast,sys; [print(x) for x in ast.literal_eval(sys.argv[1])]" "$tags_json" 2>/dev/null)

  # 遍历该实例每个 project_tag → 找 group_id → 列会话 → 采集
  for tag in "${tags[@]}"; do
    info "--- 标签: $tag ---"
    local group_id
    if [[ "$DRY_RUN" -eq 0 ]]; then
      group_id=$(get_feed_group_id "$instance" "$tag")
      if [[ "$group_id" != ofg_* ]]; then
        err "获取标签 '$tag' 的 group_id 失败: $group_id"
        continue
      fi
      info "标签 '$tag' group_id: $group_id"
    else
      info "[dry-run] 将查标签 '$tag' 的 group_id 并列会话采集"
      continue
    fi

    local raw; raw=$(get_chat_list "$group_id")
    echo "$raw" | python3 "$TOOLS" cmd_list | while IFS= read -r line; do
      local fields; fields=$(echo "$line" | python3 "$TOOLS" cmd_parse_one)
      process_chat "$(echo "$fields" | sed -n '1p')" "$(echo "$fields" | sed -n '2p')" \
                   "$(echo "$fields" | sed -n '3p')" "$instance" "$group_id"
    done
  done
}

# === 入口 ===
main() {
  info "开始采集..."

  if [[ "$DRY_RUN" -eq 0 ]]; then
    # 记录原 profile，注册 trap：正常退出/中断/出错都恢复
    ORIGINAL_PROFILE=$(get_active_profile)
    trap 'restore_profile "$ORIGINAL_PROFILE"' EXIT
  fi

  # --feed-id：旧接口，只采指定会话（用首个实例 profile）
  if [[ -n "$TARGET_FEED_ID" ]]; then
    local first_inst; first_inst=$(python3 "$SCRIPT_DIR/config.py" instances 2>/dev/null | head -1)
    [[ -z "$first_inst" ]] && { err "config 无飞书实例"; exit 1; }
    local lark_profile; lark_profile=$(python3 "$SCRIPT_DIR/config.py" instance "$first_inst" --field lark_profile 2>/dev/null)
    [[ "$DRY_RUN" -eq 0 ]] && lark-cli profile use "$lark_profile" >/dev/null 2>&1
    local group_id; group_id=$(get_feed_group_id "$first_inst")
    local raw; raw=$(get_chat_list "$group_id")
    local line; line=$(echo "$raw" | python3 "$TOOLS" cmd_list | python3 -c "
import json,sys
t='$TARGET_FEED_ID'
for l in sys.stdin:
    if json.loads(l.strip()).get('feed_id')==t: print(l.strip());sys.exit(0)
sys.exit(1)" 2>/dev/null)
    [[ -z "$line" ]] && { err "未找到 $TARGET_FEED_ID"; exit 1; }
    local fields; fields=$(echo "$line" | python3 "$TOOLS" cmd_parse_one)
    process_chat "$(echo "$fields" | sed -n '1p')" "$(echo "$fields" | sed -n '2p')" \
                 "$(echo "$fields" | sed -n '3p')" "$first_inst" "$group_id"
    ok "采集完成"
    return
  fi

  # 确定要遍历的实例列表（无参 / --all 遍历全部；--instance 指定单实例）
  local instances=()
  if [[ -n "$TARGET_INSTANCE" ]]; then
    instances=("$TARGET_INSTANCE")
  else
    while IFS= read -r name; do instances+=("$name"); done < <(python3 "$SCRIPT_DIR/config.py" instances 2>/dev/null)
  fi

  if [[ ${#instances[@]} -eq 0 ]]; then
    err "config 无飞书实例；检查 config.yaml 的 channels.feishu"
    exit 1
  fi
  info "将遍历实例: ${instances[*]}"

  for inst_name in "${instances[@]}"; do
    local lark_profile
    lark_profile=$(python3 "$SCRIPT_DIR/config.py" instance "$inst_name" --field lark_profile 2>/dev/null)
    collect_for_instance "$inst_name" "$lark_profile"
  done

  ok "采集完成"
}

main
