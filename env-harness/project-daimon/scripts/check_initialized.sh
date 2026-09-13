#!/bin/bash
# Check if project has already been initialized by project-daimon

set -e

PROJECT_ROOT="${1:-$(pwd)}"

# Check for initialization markers
GIT_DIR="$PROJECT_ROOT/.git"
CLAUDE_DIR="$PROJECT_ROOT/.claude"
OPENCODE_DIR="$PROJECT_ROOT/.opencode"
GITIGNORE="$PROJECT_ROOT/.gitignore"

# Check if any marker exists (directory or .gitignore marker)
if [ -d "$GIT_DIR" ] || [ -d "$CLAUDE_DIR" ] || [ -d "$OPENCODE_DIR" ]; then
	echo "✅ 已初始化"
	exit 0
fi

# Also check .gitignore for skill marker (covers edge case where
# directories were cleaned up but .gitignore still has the marker)
# 兼容旧版 project-scaffold 标记：旧版初始化的项目视为已初始化
if [ -f "$GITIGNORE" ] && grep -Eq "# (project-daimon|project-scaffold)" "$GITIGNORE"; then
	echo "✅ 已初始化"
	exit 0
fi

echo "❌ 未初始化"
exit 1
