#!/bin/bash
# Create .claude directory structure and CLAUDE.md

set -e

PROJECT_ROOT="${1:-$(pwd)}"
MCP_LIST="${2:-}" # Optional: comma-separated MCP names
CLAUDE_DIR="$PROJECT_ROOT/.claude"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

# Create directory structure
echo "🔧 Creating .claude directory structure..."
mkdir -p "$CLAUDE_DIR/skills"
mkdir -p "$CLAUDE_DIR/references"
mkdir -p "$CLAUDE_DIR/prompts"

# Check if CLAUDE.md already exists
if [ -f "$PROJECT_ROOT/CLAUDE.md" ]; then
	echo "⚠️  CLAUDE.md already exists, skipping creation"
else
	echo "📝 Creating CLAUDE.md..."
	# Copy template
	if [ -f "$SKILL_DIR/assets/CLAUDE.md.template" ]; then
		cp "$SKILL_DIR/assets/CLAUDE.md.template" "$PROJECT_ROOT/CLAUDE.md"
		# Replace MCP placeholder with actual or generic note
		if [ -n "$MCP_LIST" ]; then
			MCP_ENTRIES=$(echo "$MCP_LIST" | tr ',' '\n' | sed 's/^/- /')
		else
			MCP_ENTRIES="- MCP 服务器由 project-daimon 根据初始化选择自动配置"
		fi
		if command -v gsed &>/dev/null; then
			gsed -i "s|<!-- MCP_SECTION_PLACEHOLDER -->|$MCP_ENTRIES|" "$PROJECT_ROOT/CLAUDE.md"
		else
			sed -i '' "s|<!-- MCP_SECTION_PLACEHOLDER -->|$MCP_ENTRIES|" "$PROJECT_ROOT/CLAUDE.md"
		fi
		echo "✅ CLAUDE.md created from template"
	else
		# Fallback to embedded template
		cat >"$PROJECT_ROOT/CLAUDE.md" <<'EOF'
# Project Instructions

<!--
project-scaffold
此文件由 project-scaffold skill 生成
-->

本项目使用中文进行沟通。

## Git 工作流

- 修改任何 Markdown 文件后，必须立即提交 git commit
- Commit 消息应使用中文，清晰描述修改内容
- 格式：`git commit -m "修改内容描述"`

## 开发规范

- 代码注释使用中文
- Commit 消息使用中文
- 文档使用中文编写

## Claude Code 使用

本项目使用 project-daimon 管理 MCP 服务器配置。
实际安装的 MCP 取决于初始化时的选择。
如需修改 MCP 配置，请编辑 `.skillshare/mcp-bridge/servers.yaml` 后运行 `mcp-bridge.py sync`。

## 注意事项

- 请确保所有环境变量已正确配置
- 如需修改 MCP 配置，请编辑 `.claude/mcp_config.json`
EOF
		echo "✅ CLAUDE.md created"
	fi
fi

echo "✅ .claude directory structure created"
