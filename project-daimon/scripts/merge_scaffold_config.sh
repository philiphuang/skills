#!/bin/bash
# Merge project-scaffold config into existing project

set -e

PROJECT_ROOT="${1:-$(pwd)}"
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

echo "🔄 合并 project-scaffold 配置到现有项目..."

# Function to merge .gitignore
merge_gitignore() {
	local src="$1"
	local dst="$2"

	if [ ! -f "$dst" ]; then
		cp "$src" "$dst"
		echo "  ✅ 创建 .gitignore"
		return
	fi

	# Append new rules from source
	while IFS= read -r line || [ -n "$line" ]; do
		# Skip empty lines and comments
		if [[ -z "$line" ]] || [[ "$line" =~ ^# ]]; then
			continue
		fi
		# Check if rule already exists
		if ! grep -qx "$line" "$dst" 2>/dev/null; then
			echo "$line" >>"$dst"
		fi
	done <"$src"
	echo "  ✅ 合并 .gitignore"
}

# Function to merge CLAUDE.md
merge_claude_md() {
	local src="$1"
	local dst="$2"

	if [ ! -f "$dst" ]; then
		cp "$src" "$dst"
		echo "  ✅ 创建 CLAUDE.md"
		return
	fi

	# Check if skill marker already exists
	if grep -q "project-scaffold" "$dst"; then
		echo "  ⏭️  CLAUDE.md 已包含 skill 配置"
		return
	fi

	# Append separator and source content
	{
		echo ""
		echo "---"
		echo ""
		cat "$src"
	} >>"$dst"
	echo "  ✅ 合并 CLAUDE.md"
}

# Function to merge .mcp.json (requires Python)
merge_mcp_json() {
	local mcp_src="$1"
	local mcp_dst="$2"

	if [ ! -f "$mcp_dst" ]; then
		cp "$mcp_src" "$mcp_dst"
		echo "  ✅ 创建 .mcp.json"
		return
	fi

	# Use Python to merge JSON
	python3 - <<EOF
import json
import sys

try:
    with open("$mcp_src") as f:
        src_config = json.load(f)
    with open("$mcp_dst") as f:
        dst_config = json.load(f)

    # Merge mcpServers
    if "mcpServers" in src_config:
        if "mcpServers" not in dst_config:
            dst_config["mcpServers"] = {}
        dst_config["mcpServers"].update(src_config["mcpServers"])

    # Write merged config
    with open("$mcp_dst", "w") as f:
        json.dump(dst_config, f, indent=2)

    print("  ✅ 合并 .mcp.json")
except Exception as e:
    print(f"  ⚠️  合并 .mcp.json 失败: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

# Function to merge opencode.json
merge_opencode_json() {
	local opencode_src="$1"
	local opencode_dst="$2"

	if [ ! -f "$opencode_dst" ]; then
		cp "$opencode_src" "$opencode_dst"
		echo "  ✅ 创建 opencode.json"
		return
	fi

	# Use Python for deep merge
	python3 - <<EOF
import json
import sys

try:
    with open("$opencode_src") as f:
        src_config = json.load(f)
    with open("$opencode_dst") as f:
        dst_config = json.load(f)

    # Deep merge env
    if "env" in src_config:
        if "env" not in dst_config:
            dst_config["env"] = {}
        dst_config["env"].update(src_config["env"])

    # Deep merge mcp
    if "mcp" in src_config:
        if "mcp" not in dst_config:
            dst_config["mcp"] = {}
        dst_config["mcp"].update(src_config["mcp"])

    # Write merged config
    with open("$opencode_dst", "w") as f:
        json.dump(dst_config, f, indent=2)

    print("  ✅ 合并 opencode.json")
except Exception as e:
    print(f"  ⚠️  合并 opencode.json 失败: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

# Function to copy skills without overwriting
merge_skills() {
	local skills_src="$1"
	local skills_dst="$2"

	if [ ! -d "$skills_src" ]; then
		return
	fi

	if [ ! -d "$skills_dst" ]; then
		mkdir -p "$skills_dst"
	fi

	# Copy each skill if it doesn't exist
	for skill_dir in "$skills_src"/*; do
		if [ -d "$skill_dir" ]; then
			skill_name=$(basename "$skill_dir")
			if [ ! -d "$skills_dst/$skill_name" ]; then
				cp -r "$skill_dir" "$skills_dst/"
				echo "  ✅ 添加 skill: $skill_name"
			else
				echo "  ⏭️  跳过已存在的 skill: $skill_name"
			fi
		fi
	done
}

# Main merge logic
echo "项目根目录: $PROJECT_ROOT"
echo "Skill 根目录: $SKILL_ROOT"
echo ""

# Merge .gitignore
if [ -f "$SKILL_ROOT/assets/gitignore-template" ]; then
	echo "合并 .gitignore..."
	merge_gitignore "$SKILL_ROOT/assets/gitignore-template" "$PROJECT_ROOT/.gitignore"
fi

# Merge CLAUDE.md
if [ -f "$SKILL_ROOT/assets/CLAUDE.md.template" ]; then
	echo "合并 CLAUDE.md..."
	merge_claude_md "$SKILL_ROOT/assets/CLAUDE.md.template" "$PROJECT_ROOT/CLAUDE.md"
fi

# Merge .mcp.json (if exists in templates or project)
if [ -f "$PROJECT_ROOT/.mcp.json" ] || [ -f "$SKILL_ROOT/assets/.mcp.json.template" ]; then
	echo "合并 .mcp.json..."
	if [ -f "$SKILL_ROOT/assets/.mcp.json.template" ]; then
		merge_mcp_json "$SKILL_ROOT/assets/.mcp.json.template" "$PROJECT_ROOT/.mcp.json"
	else
		echo "  ⏭️  没有 MCP 配置模板"
	fi
fi

# Merge opencode.json
if [ -f "$PROJECT_ROOT/opencode.json" ] && [ -f "$SKILL_ROOT/assets/opencode.json.template" ]; then
	echo "合并 opencode.json..."
	merge_opencode_json "$SKILL_ROOT/assets/opencode.json.template" "$PROJECT_ROOT/opencode.json"
fi

# Merge skills
if [ -d "$SKILL_ROOT/.claude/skills" ]; then
	echo "合并 skills..."
	merge_skills "$SKILL_ROOT/.claude/skills" "$PROJECT_ROOT/.claude/skills"
fi

# Create TODO.md and 经验.md if they don't exist
if [ ! -f "$PROJECT_ROOT/TODO.md" ] && [ -f "$SKILL_ROOT/assets/TODO.md.template" ]; then
	cp "$SKILL_ROOT/assets/TODO.md.template" "$PROJECT_ROOT/TODO.md"
	echo "  ✅ 创建 TODO.md"
fi

if [ ! -f "$PROJECT_ROOT/经验.md" ] && [ -f "$SKILL_ROOT/assets/经验.md.template" ]; then
	cp "$SKILL_ROOT/assets/经验.md.template" "$PROJECT_ROOT/经验.md"
	echo "  ✅ 创建 经验.md"
fi

echo ""
echo "✅ 配置合并完成"
