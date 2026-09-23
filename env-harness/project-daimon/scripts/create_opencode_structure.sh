#!/bin/bash
# Create OpenCode directory structure and opencode.json

set -e

PROJECT_ROOT="${1:-$(pwd)}"
OPENCODE_DIR="$PROJECT_ROOT/.opencode"

# Create directory structure
echo "🔧 Creating .opencode directory structure..."
mkdir -p "$OPENCODE_DIR/plugin"
mkdir -p "$OPENCODE_DIR/agent"
mkdir -p "$OPENCODE_DIR/command"

# Check if opencode.json already exists
if [ -f "$PROJECT_ROOT/opencode.json" ]; then
	echo "⚠️  opencode.json already exists, skipping creation"
else
	echo "📝 Creating opencode.json..."
	SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
	TEMPLATE="$SKILL_DIR/assets/opencode.json.template"
	if [ -f "$TEMPLATE" ]; then
		cp "$TEMPLATE" "$PROJECT_ROOT/opencode.json"
		echo "✅ opencode.json created from template"
	else
		# Fallback: minimal opencode.json（根级 env 违反 Schema，不得出现 —— #16）
		cat >"$PROJECT_ROOT/opencode.json" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {}
}
EOF
		echo "✅ opencode.json created (fallback)"
	fi
fi

echo "✅ .opencode directory structure created"
