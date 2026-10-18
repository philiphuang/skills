#!/bin/bash
# collect-meetings.sh — 飞书妙记链接发现 → 转交 docness 收逐字稿（#201）
#
# 分工铁律：imness 只发现链接，docness 负责取件落库，不跳层。
#   遍历所有飞书实例 → 每个实例用「project_tags ∩ 会议记录标签」找会议发现群（#22 决策）
#   → 从这些群已采集的 raw/transcripts 提取妙记 URL → 对照已收逐字稿去重
#   → stdout 打印未收录 URL（每行一条），由调用方逐条交给 docness collect
#     （裸妙记 URL 输入即触发其 4c 会议分支，产物 {$知识库}/会议纪要/{yymmdd}-{主题}-逐字稿.txt）。
#   不调 minutes +detail、不归一化、不打码、不写 raw/meetings。
#
# 已收录判定：{$知识库}/会议纪要/*.txt frontmatter 的 source 含同 token
#   （{$知识库} 按项目说明文件 ## Docness 工作目录 解析，语义对齐 docness init_workspace；
#    解析失败时不去重，全部打印交 docness 判重）。
#   旧 raw/meetings digest 不算已收录——digest 与逐字稿是两种产物，#201 起以逐字稿为准。
#
# 入口：
#   collect-meetings.sh                    # 遍历所有实例
#   collect-meetings.sh --instance <name>  # 只扫某实例的会议发现群
#   collect-meetings.sh --dry-run          # 只打印将扫描哪些群，不发现链接
#
# 详见 imness/SKILL.md collect-meetings 段落。
set -eo pipefail
source "$(dirname "$0")/common.sh"

TRANSCRIPTS_DIR="$KNOWLEDGE_DIR/raw/transcripts"
LOG_FILE="$KNOWLEDGE_DIR/sync.log"

TARGET_INSTANCE="" DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --instance) TARGET_INSTANCE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) shift ;;
  esac
done

# === docness 知识库解析（{$知识库}） ===
# 与 docness scripts/init_workspace.py 读取语义一致：项目说明文件中首个
# 含 docness: 键（或裸工作区四键）的 yaml 围栏块 → root 相对项目根、知识库相对 root。
# 未声明/解析失败输出空串。
resolve_docness_kb() {
  IMNESS_PR="$PROJECT_ROOT" python3 - <<'PY'
import os, re, sys, yaml
root = os.environ['IMNESS_PR']
target = next((os.path.join(root, n) for n in ('AGENTS.md', 'agents.md', 'CLAUDE.md', 'claude.md')
               if os.path.isfile(os.path.join(root, n))), None)
if not target:
    print(''); sys.exit(0)
text = open(target, encoding='utf-8').read()
for m in re.finditer(r'```(?:yaml|yml)?\n(.*?)```', text, re.S):
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        continue
    if not isinstance(data, dict):
        continue
    cfg = data.get('docness') if isinstance(data.get('docness'), dict) else None
    if cfg is None and any(k in data for k in ('收件箱', '知识库', '工作台', '发件箱')):
        cfg = data
    if not isinstance(cfg, dict) or not str(cfg.get('知识库', '')).strip():
        continue
    ws_root = root
    rv = str(cfg.get('root', '') or '').strip()
    if rv:
        ws_root = rv if os.path.isabs(rv) else os.path.join(root, rv)
    kv = str(cfg['知识库']).strip()
    kb = kv if os.path.isabs(kv) else os.path.join(ws_root, kv)
    print(os.path.normpath(kb)); sys.exit(0)
print('')
PY
}

# === 已收 token 清单 ===
# 读 {$知识库}/会议纪要/*.txt 的 frontmatter（首对 --- 之间）source 行，
# 提取 minutes token。只读 frontmatter——正文可能提及其他会议链接，不代表已收录。
dump_collected_tokens() {
  local kb_dir="$1"
  [[ -z "$kb_dir" || ! -d "$kb_dir/会议纪要" ]] && return 0
  local f
  for f in "$kb_dir"/会议纪要/*.txt; do
    [[ -e "$f" ]] || continue
    awk 'NR==1 && $0!="---"{exit} NR>1{if($0=="---")exit; print}' "$f"
  done | grep -o 'minutes/obc[a-z0-9]*' | sed 's|minutes/||' | sort -u
}

# === URL 发现 ===
# 输入：transcript 文件 + 已收 token 清单文件；stdout 每行一条未收录妙记 URL，
# stderr 打印 TOTAL/NEW 计数。
scan_transcript_for_urls() {
  local transcript="$1" collected="$2"
  SCAN_TRANSCRIPT="$transcript" SCAN_COLLECTED="$collected" python3 - <<'PY'
import os, re, sys
text = open(os.environ['SCAN_TRANSCRIPT'], encoding='utf-8', errors='replace').read()
collected = set()
try:
    collected = {l.strip() for l in open(os.environ['SCAN_COLLECTED'], encoding='utf-8') if l.strip()}
except OSError:
    pass
urls, seen = [], set()
for m in re.finditer(r'(https?://[^\s<>"\']+/minutes)/(obc[a-z0-9]+)', text):
    if m.group(2) in seen:
        continue
    seen.add(m.group(2))
    urls.append(m.group(1) + '/' + m.group(2))
new = [u for u in urls if u.rsplit('/', 1)[1] not in collected]
print(f'TOTAL:{len(urls)} NEW:{len(new)}', file=sys.stderr)
for u in new:
    print(u)
PY
}

discover_for_instance() {
  local instance="$1" lark_profile="$2" collected="$3"
  info "=== 实例: $instance (会议链接发现) ==="

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

  # 对每个会议发现群，找对应 raw transcript 提取妙记 URL
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

    mapfile -t NEW_URLS < <(scan_transcript_for_urls "$transcript" "$collected")
    info "  待转交: ${#NEW_URLS[@]} 条"
    for url in "${NEW_URLS[@]}"; do
      echo "$url"
      # 记入已收集合，防同轮多群重复输出同一 token
      echo "${url##*/}" >> "$collected"
      total_new=$((total_new + 1))
    done
  done

  echo "$(date +%Y-%m-%dT%H:%M:%S+08:00) | [$instance] 妙记链接发现 | 新增 $total_new | 转交 docness 收逐字稿" >> "$LOG_FILE"
  ok "实例 $instance 链接发现完成: 未收录 $total_new 条（转交 docness collect）"
}

# === 入口 ===
main() {
  info "开始会议妙记链接发现..."

  if [[ "$DRY_RUN" -eq 0 ]]; then
    ORIGINAL_PROFILE=$(get_active_profile)
    trap 'restore_profile "$ORIGINAL_PROFILE"' EXIT
  fi

  local kb_dir
  kb_dir=$(resolve_docness_kb)
  if [[ -n "$kb_dir" ]]; then
    info "docness 知识库: $kb_dir（已收逐字稿参与去重）"
  else
    warn "未解析到 docness 工作区声明——不去重，全部打印交 docness 判重"
  fi

  local tmp_collected
  tmp_collected=$(mktemp)
  dump_collected_tokens "$kb_dir" > "$tmp_collected" || true

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
    discover_for_instance "$inst_name" "$lark_profile" "$tmp_collected"
  done

  rm -f "$tmp_collected"
  ok "会议妙记链接发现完成（stdout 的 URL 逐条交 docness collect 收逐字稿）"
}

main
