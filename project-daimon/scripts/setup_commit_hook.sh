#!/bin/bash
# Setup auto-commit hook for markdown files

set -e

PROJECT_ROOT="${1:-$(pwd)}"
TOOLS="${2:-claude}"

echo "🔧 Setting up auto-commit hook..."

# Claude Code: Add hook to CLAUDE.md
if [[ "$TOOLS" == *"claude"* ]] || [[ "$TOOLS" == *"Claude"* ]]; then
    CLAUDE_MD="$PROJECT_ROOT/.claude/CLAUDE.md"

    if [ -f "$CLAUDE_MD" ]; then
        # Check if hook already exists
        if ! grep -q "postToolUse" "$CLAUDE_MD"; then
            echo "" >> "$CLAUDE_MD"
            echo "## Auto-commit Hook" >> "$CLAUDE_MD"
            echo "" >> "$CLAUDE_MD"
            echo "修改任何 .md 文件后自动提交 git commit：" >> "$CLAUDE_MD"
            echo '```bash' >> "$CLAUDE_MD"
            echo 'git add "\$FILE" && git commit -m "更新文档: \$FILE"' >> "$CLAUDE_MD"
            echo '```' >> "$CLAUDE_MD"
            echo "✅ Added hook to CLAUDE.md"
        else
            echo "⚠️  Hook already exists in CLAUDE.md"
        fi
    fi
fi

# OpenCode: Create a plugin for file watching
if [[ "$TOOLS" == *"opencode"* ]] || [[ "$TOOLS" == *"OpenCode"* ]]; then
    PLUGIN_DIR="$PROJECT_ROOT/.opencode/plugin"
    mkdir -p "$PLUGIN_DIR"

    PLUGIN_FILE="$PLUGIN_DIR/auto-commit.js"
    if [ ! -f "$PLUGIN_FILE" ]; then
        cat > "$PLUGIN_FILE" << 'EOF'
// Auto-commit plugin for OpenCode
module.exports = {
  name: 'auto-commit',
  hooks: {
    'file.edited': async ({ filePath }) => {
      if (filePath.endsWith('.md')) {
        const { exec } = require('child_process');
        exec(`git add "${filePath}" && git commit -m "更新文档: ${filePath}"`);
      }
    }
  }
};
EOF
        echo "✅ Created auto-commit plugin for OpenCode"
    else
        echo "⚠️  Auto-commit plugin already exists"
    fi
fi

echo "✅ Auto-commit hook setup complete"
