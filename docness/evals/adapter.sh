#!/usr/bin/env bash
# Docness OpenCode Adapter for skill-up custom engine transport.
# Contract: reads SessionInput JSON → calls opencode → writes SessionResult JSON.
#
# Usage: adapter.sh --input <input_file> --output <output_file> --workspace <dir>

set -euo pipefail
INPUT_FILE=""
OUTPUT_FILE=""
WORKSPACE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)  INPUT_FILE="$2"; shift 2 ;;
    --output) OUTPUT_FILE="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$INPUT_FILE" || -z "$OUTPUT_FILE" ]]; then
  echo '{"exit_code":1,"final_message":"adapter: missing --input or --output","duration_ms":0}' > "${OUTPUT_FILE:-/dev/null}"
  exit 0
fi

START_TS=$(python3 -c 'import time; print(int(time.time()*1000))')

# Source test env from project root
PROJECT_ROOT="/Users/philiphuang/projects/ai_zhuanban"
if [[ -f "$PROJECT_ROOT/.env.test" ]]; then
  set -a; source "$PROJECT_ROOT/.env.test"; set +a
fi

# Clean project workspace
for d in 收件箱 知识库 工作台 发件箱; do
  rm -rf "$PROJECT_ROOT/$d"/* 2>/dev/null || true
done
rm -rf "$PROJECT_ROOT/.logs"/* 2>/dev/null || true

# Copy fixtures to project (baseline for tests)
if [[ -d "$PROJECT_ROOT/test/fixtures" ]]; then
  cp -r "$PROJECT_ROOT/test/fixtures"/* "$PROJECT_ROOT/" 2>/dev/null || true
fi

# Switch to test lark-cli profile
lark-cli profile use test 2>/dev/null || true

# Switch to project root (skill-up sandbox allows internal cd)
cd "$PROJECT_ROOT"

# Parse SessionInput → extract prompt
PROMPT=$(python3 -c "
import json, sys
with open('$INPUT_FILE') as f:
    data = json.load(f)
msgs = data.get('messages', [])
content = msgs[0].get('content', '') if msgs else ''
print(content)
" 2>/dev/null || true)

if [[ -z "$PROMPT" ]]; then
  END_TS=$(python3 -c 'import time; print(int(time.time()*1000))')
  ELAPSED=$((END_TS - START_TS))
  echo "{\"exit_code\":1,\"final_message\":\"adapter: empty prompt\",\"duration_ms\":$ELAPSED}" > "$OUTPUT_FILE"
  exit 0
fi

# Run opencode, capturing real exit code even with set -e
TIMEOUT=1200
START_NS=$(python3 -c 'import time; print(int(time.time()*1e9))')
set +e
OP_OUTPUT=$(timeout $TIMEOUT opencode run \
  "$PROMPT" \
  --auto \
  --dir "$PROJECT_ROOT" \
  --model "kimi-dengdi/kimi-for-coding" \
  2>&1)
EXIT_CODE=$?
set -e
END_NS=$(python3 -c 'import time; print(int(time.time()*1e9))')
DURATION=$(( (END_NS - START_NS) / 1000000 ))

# Wrap in SessionResult JSON, creating output dir if needed
mkdir -p "$(dirname "$OUTPUT_FILE")"

# Copy project workspace results back to skill-up workspace for file checking
for d in 收件箱 知识库 工作台 发件箱 .logs; do
  if [[ -d "$PROJECT_ROOT/$d" ]]; then
    cp -r "$PROJECT_ROOT/$d" "$WORKSPACE/" 2>/dev/null || true
  fi
done

# Switch back to production profile
lark-cli profile use production 2>/dev/null || true

python3 -c "
import json, sys
result = {
    'exit_code': $EXIT_CODE,
    'final_message': $(echo "$OP_OUTPUT" | python3 -c 'import json,sys; json.dump(sys.stdin.read()[:8000], sys.stdout)'),
    'duration_ms': $DURATION
}
with open('$OUTPUT_FILE', 'w') as f:
    json.dump(result, f, ensure_ascii=False)
"
