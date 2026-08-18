#!/bin/bash
# common.sh — imness 所有脚本共享的工具函数
# source: source "$(dirname "$0")/common.sh"
#
# 路径约定（见 imness/SKILL.md 架构）：
#   imness/scripts/  ← 本文件所在
#   imness/          ← SCRIPT_DIR/..  (REPO_ROOT 的相对基准)
#   knowledge/       ← 项目根的知识库目录（REPO_ROOT 同级）
# 项目根 = scripts 目录的上两级

set -eo pipefail

info()  { printf '\033[36m[信息]\033[0m %s\n' "$1" >&2; }
ok()    { printf '\033[32m[完成]\033[0m %s\n' "$1" >&2; }
warn()  { printf '\033[33m[警告]\033[0m %s\n' "$1" >&2; }
err()   { printf '\033[31m[错误]\033[0m %s\n' "$1" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMNESS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"          # imness/
PROJECT_ROOT="$(cd "$IMNESS_DIR/.." && pwd)"        # MCloud 项目根
KNOWLEDGE_DIR="$PROJECT_ROOT/knowledge"
WIKI_DIR="$KNOWLEDGE_DIR/wiki"
CONFIG_FILE="$IMNESS_DIR/config.yaml"
REDACT_PY="$SCRIPT_DIR/redact.py"
TOOLS_PY="$SCRIPT_DIR/chat_tools.py"

# 读取 config.yaml 的 feed group 标签名（第一个标签对应的 group_id）
# 依赖 python3 + pyyaml
#
# 多实例支持（#24）：
#   get_feed_group_id [instance_name] [tag]
#   - 有 instance：经 config.py 读该实例的 project_tags，返回对应 group_id。
#     第二个参数 $2 指定标签名（缺省取实例第一个标签）。
#   - 无 instance：走旧逻辑（顶层 feed_groups[0]）。
get_feed_group_id() {
  local instance="${1:-}" tag="${2:-}"
  if [[ -z "$instance" ]]; then
    python3 -c "
import yaml, json, sys
with open('$CONFIG_FILE') as f:
    cfg = yaml.safe_load(f)
groups = cfg.get('feed_groups', [])
if not groups:
    sys.exit('config.yaml 无 feed_groups 配置')
tag = groups[0]
import subprocess
out = subprocess.run(['lark-cli','im','+feed-group-list','--format','json'],
                     capture_output=True, text=True)
data = json.loads(out.stdout)
for g in data.get('data', {}).get('groups', []):
    if g.get('name') == tag:
        print(g.get('group_id'))
        sys.exit(0)
sys.exit(f'未在飞书找到标签: {tag}')
" 2>&1
    return
  fi
  # 多实例路径：经 config.py 取该实例 project_tags，再查 lark group_id
  local tags
  tags=$(python3 "$SCRIPT_DIR/config.py" instance "$instance" --field project_tags 2>&1) || {
    err "config.py 读取实例 $instance 失败: $tags"
    return 1
  }
  # --field project_tags 输出 python list 字面量（如 [agent]），取第一个元素
  [[ -z "$tag" ]] && tag=$(python3 -c "import ast,sys; print(ast.literal_eval(sys.stdin.read())[0])" <<< "$tags" 2>/dev/null || echo "$tags")
  # 经环境变量传 tag，避免字符串注入风险
  IMNESS_TAG="$tag" python3 -c "
import json, os, subprocess, sys
tag = os.environ['IMNESS_TAG']
out = subprocess.run(['lark-cli','im','+feed-group-list','--format','json'],
                     capture_output=True, text=True)
data = json.loads(out.stdout)
for g in data.get('data', {}).get('groups', []):
    if g.get('name') == tag:
        print(g.get('group_id'))
        sys.exit(0)
sys.exit(f'未在飞书找到标签: {tag}')
" 2>&1
}

# 文件名清洗：把不安全的字符替换/删除，使其可作文件名。
# / 与空格 → _；< > : " | ? * 删除；默认截断到 40 字符（与 collect-meetings 一致）。
# 所有 collect 脚本共用，避免文件名规则 drift。
sanitize_filename() {
  local raw="$1"
  local max_len="${2:-40}"
  echo "$raw" | sed 's/[/ ]/_/g; s/[<>:"|?*]//g' | cut -c1-"$max_len"
}

# === profile 切换恢复（#24 决策：串行采集，采完恢复原 active profile）===
# 供 collect-chats.sh / collect-meetings.sh 共享，避免二重身。

get_active_profile() {
  lark-cli profile list 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for p in data:
    if p.get('active'):
        print(p['name'])
        break
" 2>/dev/null
}

# 注册 trap: trap 'restore_profile "$ORIGINAL_PROFILE"' EXIT
# ORIGINAL_PROFILE 由调用方在 main() 中设置
restore_profile() {
  local profile="${1:-}"
  if [[ -n "$profile" ]]; then
    info "恢复 profile: $profile"
    lark-cli profile use "$profile" >/dev/null 2>&1 || warn "恢复 profile 失败（非致命）"
  fi
}

# instance_flag <instance_name> → 输出 "--instance <name>"（空字符串则无输出）
# 用法: python3 "$TOOLS" cmd_xxx $(instance_flag "$instance")
#       或 local -a flags=(cmd_xxx $(instance_flag "$instance"))
# 消除两脚本中 6 处重复的 --instance 条件构造模式（Repeated Switches smell）。
instance_flag() {
  local instance="${1:-}"
  [[ -n "$instance" ]] && printf '%s %s' '--instance' "$instance"
}

# get_meeting_chats <instance_name> — 标签匹配找会议发现群（#22 决策）。
#
# 会议发现群 = 同时具有「本实例 project_tags 任一」和「会议记录」标签的群。
# 输出每行一个 chat_id（可能多个群）。
#
# 本函数是此逻辑的唯一处所——从 config.py 移出（#25 review Item 3），
# 使 config.py 保持纯 config 读取，lark-cli 调用归位到 common.sh。
get_meeting_chats() {
  local instance="$1"
  local meeting_tag="${2:-会议记录}"

  # 取该实例的 project_tags（经 config.py）
  local tags_json
  tags_json=$(python3 "$SCRIPT_DIR/config.py" instance "$instance" --field project_tags 2>/dev/null) || {
    err "config.py 读取实例 $instance project_tags 失败"
    return 1
  }

  # 辅助：查某标签下所有 feed_id
  _feed_ids_in_tag() {
    local tag_name="$1"
    local group_id
    group_id=$(python3 -c "
import json, subprocess, sys, os
tag = os.environ.get('IMNESS_TAG','')
out = subprocess.run(['lark-cli','im','+feed-group-list','--format','json'],
                     capture_output=True, text=True)
data = json.loads(out.stdout)
for g in data.get('data',{}).get('groups',[]):
    if g.get('name') == tag:
        print(g.get('group_id'))
        sys.exit(0)
" 2>/dev/null)
    [[ -z "$group_id" ]] && return
    # 列该标签下所有 feed_id
    lark-cli im +feed-group-list-item --feed-group-id "$group_id" --page-all --format json 2>/dev/null \
      | python3 -c "import json,sys; [print(i['feed_id']) for i in json.load(sys.stdin).get('data',{}).get('items',[]) if i.get('feed_id')]"
  }

  # project_tags 各标签下的 chat_id 集合
  local tmp_project; tmp_project=$(mktemp)
  while IFS= read -r tag; do
    [[ -z "$tag" ]] && continue
    IMNESS_TAG="$tag" _feed_ids_in_tag "$tag" 2>/dev/null
  done < <(python3 -c "import ast,sys; [print(x) for x in ast.literal_eval(sys.argv[1])]" "$tags_json" 2>/dev/null) \
    | sort -u > "$tmp_project"

  # 「会议记录」标签下的 chat_id 集合
  local tmp_meeting; tmp_meeting=$(mktemp)
  IMNESS_TAG="$meeting_tag" _feed_ids_in_tag "$meeting_tag" 2>/dev/null | sort -u > "$tmp_meeting"

  # 交集
  comm -12 "$tmp_project" "$tmp_meeting" 2>/dev/null
  rm -f "$tmp_project" "$tmp_meeting"
}
