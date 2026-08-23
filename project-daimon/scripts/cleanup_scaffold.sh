#!/bin/bash
# Cleanup files created by project-scaffold skill

set -e

PROJECT_ROOT="${1:-$(pwd)}"

echo "🧹 清理 project-scaffold 产生的文件..."

# Function to remove safely
safe_remove() {
    if [ -e "$1" ]; then
        echo "  删除: $1"
        rm -rf "$1"
    fi
}

# Remove Git repository (only if initialized by this skill)
if [ -f "$PROJECT_ROOT/.gitignore" ] && grep -q "# project-scaffold" "$PROJECT_ROOT/.gitignore" 2>/dev/null; then
    safe_remove "$PROJECT_ROOT/.git"
fi

# Remove .claude directory
safe_remove "$PROJECT_ROOT/.claude"

# Remove .opencode directory
safe_remove "$PROJECT_ROOT/.opencode"

# Remove .gitignore (only if created by this skill)
if [ -f "$PROJECT_ROOT/.gitignore" ] && grep -q "# project-scaffold" "$PROJECT_ROOT/.gitignore" 2>/dev/null; then
    safe_remove "$PROJECT_ROOT/.gitignore"
fi

# Remove CLAUDE.md (only if created by this skill)
if [ -f "$PROJECT_ROOT/CLAUDE.md" ]; then
    if grep -q "# project-scaffold" "$PROJECT_ROOT/CLAUDE.md" 2>/dev/null; then
        safe_remove "$PROJECT_ROOT/CLAUDE.md"
    fi
fi

# Remove opencode.json (only if created by this skill)
if [ -f "$PROJECT_ROOT/opencode.json" ]; then
    if grep -q "# project-scaffold" "$PROJECT_ROOT/opencode.json" 2>/dev/null; then
        safe_remove "$PROJECT_ROOT/opencode.json"
    fi
fi

echo "✅ 清理完成"
