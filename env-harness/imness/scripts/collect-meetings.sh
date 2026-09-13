#!/bin/bash
# collect-meetings.sh — 飞书会议妙记采集 → knowledge/raw/meetings/
#
# 多实例 + 标签匹配发现（#25 落地，#22 决策）：
#   遍历所有飞书实例 → 每个实例用「project_tags ∩ 会议记录标签」找会议发现群
#   → 从这些群已采集的 raw/transcripts 提取妙记链接 → lark-minutes +detail
#   拉结构化产物 → 归一化（含 redact 打码 + source frontmatter）→ 写 raw/meetings
#
# 入口：
#   collect-meetings.sh                    # 遍历所有实例
#   collect-meetings.sh --instance <name>  # 只采某实例的会议发现群
#   collect-meetings.sh --dry-run          # 只打印将扫描哪些群，不拉妙记
#
# 详见 imness/SKILL.md collect-meetings 段落。
set -eo pipefail
source "$(dirname "$0")/common.sh"

MEETINGS_DIR="$KNOWLEDGE_DIR/raw/meetings"
TRANSCRIPTS_DIR="$KNOWLEDGE_DIR/raw/transcripts"
LOG_FILE="$KNOWLEDGE_DIR/sync.log"
TOOLS="$TOOLS_PY"

TARGET_INSTANCE="" DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --instance) TARGET_INSTANCE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) shift ;;
  esac
done

mkdir -p "$MEETINGS_DIR"

# === token 扫描与采集 ===
# 输出：每行一个 token（已过滤 raw/meetings 下存在的）
scan_transcript_for_tokens() {
  local transcript="$1"
  python3 -c "
import re, os, sys
text = open('$transcript').read()
seen = set()
tokens = []
for m in re.finditer(r'minutes/(obc[a-z0-9]+)', text):
    t = m.group(1)
    if t not in seen:
        seen.add(t)
        tokens.append(t)
meetings_dir = '$MEETINGS_DIR'
existing = os.listdir(meetings_dir) if os.path.isdir(meetings_dir) else []
new = [t for t in tokens if not any(t[:12] in f for f in existing)]
print(f'TOTAL:{len(tokens)} NEW:{len(new)}', file=sys.stderr)
for t in new:
    print(t)
" 2>"$MEETINGS_DIR/.scan.log"
}

collect_one() {
  local token="$1" instance="$2"
  local start_ts; start_ts=$(date +%s)
  info "拉取妙记: $token"

  local raw_detail
  raw_detail=$(lark-cli minutes +detail --minute-tokens "$token" \
    --summary --todo --chapter --keyword --format json 2>/dev/null) || { warn "拉取 $token 失败"; return 1; }

  # 归一化（内部调 redact 打码；--instance 写 source frontmatter）
  local result title token_out file_name file_path
  local -a norm_flags=(cmd_normalize_meeting $(instance_flag "$instance"))
  result=$(echo "$raw_detail" | python3 "$TOOLS" "${norm_flags[@]}" 2>/dev/null) || { warn "归一化 $token 失败"; return 1; }
  token_out=$(echo "$result" | grep 'MEETING_TOKEN:' | sed 's/MEETING_TOKEN://')
  # 标题：跳过 frontmatter（若有）找首个 # 行
  title=$(echo "$result" | grep -m1 '^# ' | sed 's/^# //')
  title="${title:-未知会议}"

  local safe_title; safe_title=$(sanitize_filename "$title")
  file_name="${safe_title}_${token:0:12}.md"
  file_path="$MEETINGS_DIR/$file_name"

  echo "$result" | sed '/MEETING_TOKEN:/d' > "$file_path"

  local d; d=$(($(date +%s) - start_ts))
  echo "$(date +%Y-%m-%dT%H:%M:%S+08:00) | [$instance] 妙记:$title | 新增 | token=${token:0:12} | ${d}s" >> "$LOG_FILE"
  ok "  [$instance] $title → $file_name (${d}s)"
}

collect_for_instance() {
  local instance="$1" lark_profile="$2"
  info "=== 实例: $instance (会议采集) ==="

  if [[ "$DRY_RUN" -eq 0 ]]; then
    lark-cli profile use "$lark_profile" >/dev/null 2>&1 || warn "profile 切换失败（继续）"
  fi

  # #22 标签匹配：project_tags ∩ 「会议记录」标签 → 会议发现群（可能多个）
  # get_meeting_chats 在 common.sh，lark-cli 调用归位（#25 review Item 3）
  local meeting_chats=()
  if [[ "$DRY_RUN" -eq 0 ]]; then
    while IFS= read -r cid; do [[ -n "$cid" ]] && meeting_chats+=("$cid"); done \
      < <(get_meeting_chats "$instance" 2>/dev/null)
  else
    info "[dry-run] 将用 get_meeting_chats $instance 查会议发现群"
    return
  fi

  if [[ ${#meeting_chats[@]} -eq 0 ]]; then
    warn "实例 $instance 无会议发现群（需在飞书把群同时加入 project_tags 标签和「会议记录」标签）"
    return
  fi
  info "会议发现群: ${meeting_chats[*]}"

  # 对每个会议发现群，找对应 raw transcript 提取妙记 token
  local total_new=0
  for chat_id in "${meeting_chats[@]}"; do
    # transcript 文件名含 chat_id 前 12 位
    local transcript
    transcript=$(find "$TRANSCRIPTS_DIR" -name "*${chat_id:0:12}*" 2>/dev/null | head -1)
    if [[ -z "$transcript" ]]; then
      warn "群 $chat_id 的 transcript 未找到（先运行 collect-chats.sh 采集该群）"
      continue
    fi
    info "扫描 transcript: $(basename "$transcript")"

    mapfile -t NEW_TOKENS < <(scan_transcript_for_tokens "$transcript")
    local scan_info; scan_info=$(cat "$MEETINGS_DIR/.scan.log" 2>/dev/null)
    info "  $scan_info | 待采集: ${#NEW_TOKENS[@]} 个"

    for token in "${NEW_TOKENS[@]}"; do
      collect_one "$token" "$instance" || continue
      total_new=$((total_new + 1))
    done
  done

  ok "实例 $instance 会议采集完成: 新增 $total_new 个"
}

# === 入口 ===
main() {
  info "开始会议妙记采集..."

  if [[ "$DRY_RUN" -eq 0 ]]; then
    ORIGINAL_PROFILE=$(get_active_profile)
    trap 'restore_profile "$ORIGINAL_PROFILE"' EXIT
  fi

  local instances=()
  if [[ -n "$TARGET_INSTANCE" ]]; then
    instances=("$TARGET_INSTANCE")
  else
    while IFS= read -r name; do instances+=("$name"); done < <(python3 "$SCRIPT_DIR/config.py" instances 2>/dev/null)
  fi

  [[ ${#instances[@]} -eq 0 ]] && { err "config 无飞书实例"; exit 1; }

  for inst_name in "${instances[@]}"; do
    local lark_profile
    lark_profile=$(python3 "$SCRIPT_DIR/config.py" instance "$inst_name" --field lark_profile 2>/dev/null)
    collect_for_instance "$inst_name" "$lark_profile"
  done

  ok "会议妙记采集完成"
}

main
