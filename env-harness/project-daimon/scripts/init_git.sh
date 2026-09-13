#!/bin/bash
# Initialize git repository and setup basic configuration

set -e

PROJECT_ROOT="${1:-$(pwd)}"

# Check if already a git repository
if [ -d "$PROJECT_ROOT/.git" ]; then
	echo "⚠️  Git repository already initialized"
	exit 0
fi

# Initialize git repository
echo "🔧 Initializing git repository..."
cd "$PROJECT_ROOT" && git init

# Set default branch to main
cd "$PROJECT_ROOT" && (git checkout -b main 2>/dev/null || git branch -M main)

echo "✅ Git repository initialized"
