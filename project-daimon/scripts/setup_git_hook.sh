#!/bin/bash
# Setup Git native post-commit hook for auto-commit
# 这个 hook 会在任何 git commit 后自动执行

set -e

PROJECT_ROOT="${1:-$(pwd)}"
HOOK_FILE="$PROJECT_ROOT/.git/hooks/post-commit"

echo "🔧 Setting up Git native auto-commit hook..."

# 检查是否在 git 仓库中
if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo "❌ 不是 git 仓库"
    exit 1
fi

# 创建 post-commit hook
cat > "$HOOK_FILE" << 'HOOK'
#!/bin/bash
# Git post-commit hook
# 自动修正 commit 消息格式为 Conventional Commits

# 获取最新的 commit 消息
LAST_MSG=$(git log -1 --format=%s)

# 如果消息不是 Conventional Commits 格式，则修改
if ! echo "$LAST_MSG" | grep -qE "^(feat|fix|docs|style|refactor|test|chore|perf)(\(.+\))?: "; then
    # 获取变更的文件
    CHANGED_FILES=$(git diff --name-only HEAD~1 HEAD)
    FILE_COUNT=$(echo "$CHANGED_FILES" | wc -l | tr -d ' ')

    # 分析文件类型
    MAIN_EXT=$(echo "$CHANGED_FILES" | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')

    # 生成智能消息
    case "$MAIN_EXT" in
        md)
            NEW_MSG="docs: 更新文档"
            ;;
        sh)
            NEW_MSG="chore: 更新脚本"
            ;;
        ts|js)
            NEW_MSG="refactor: 更新代码"
            ;;
        json|yaml)
            NEW_MSG="chore: 更新配置"
            ;;
        *)
            NEW_MSG="chore: 更新 ${FILE_COUNT} 个文件"
            ;;
    esac

    # 修正 commit 消息
    git commit --amend -m "$NEW_MSG" --no-verify
    echo "📝 Commit 消息已修正: $LAST_MSG → $NEW_MSG"
fi
HOOK

chmod +x "$HOOK_FILE"

echo "✅ Git native hook 已安装: $HOOK_FILE"
echo ""
echo "现在任何 git commit 都会自动修正消息格式！"
