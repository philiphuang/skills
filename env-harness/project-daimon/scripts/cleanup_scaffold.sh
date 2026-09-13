#!/bin/bash
# Cleanup files created by project-daimon skill
# 兼容旧版 project-scaffold 标记：旧版初始化的项目同样识别为 skill 产物

set -e

PROJECT_ROOT="${1:-$(pwd)}"

echo "🧹 清理 project-daimon 产生的文件..."

# Function to remove safely
safe_remove() {
    if [ -e "$1" ]; then
        echo "  删除: $1"
        rm -rf "$1"
    fi
}

# Skill 标记匹配：兼容新旧两代（project-scaffold → project-daimon）
# 匹配形态：gitignore 的 `# project-daimon`、模板的 HTML 注释
# `<!-- 此文件由 project-daimon skill 生成 -->`、旧版 `project-scaffold`
marker_match() {
    grep -Eq "# (project-daimon|project-scaffold)|project-(daimon|scaffold) skill" "$1" 2>/dev/null
}

# Remove Git repository (only if initialized by this skill)
# .git 删除为不可逆操作（含未 push 分支/stash），先确认一次
if [ -d "$PROJECT_ROOT/.git" ] && [ -f "$PROJECT_ROOT/.gitignore" ] && marker_match "$PROJECT_ROOT/.gitignore"; then
    echo "⚠️  将删除整个 .git 仓库（含未推送分支与 stash）"
    read -r -p "  确认删除？[y/N] " git_confirm < /dev/tty
    case "$git_confirm" in
        y|Y|yes|YES)
            safe_remove "$PROJECT_ROOT/.git"
            ;;
        *)
            echo "  ⏭️  跳过 .git 删除，保留 git 仓库"
            ;;
    esac
fi

# Remove .claude directory
safe_remove "$PROJECT_ROOT/.claude"

# Remove .opencode directory
safe_remove "$PROJECT_ROOT/.opencode"

# Remove .gitignore (only if created by this skill)
if [ -f "$PROJECT_ROOT/.gitignore" ] && marker_match "$PROJECT_ROOT/.gitignore"; then
    safe_remove "$PROJECT_ROOT/.gitignore"
fi

# Remove CLAUDE.md (only if created by this skill)
if [ -f "$PROJECT_ROOT/CLAUDE.md" ] && marker_match "$PROJECT_ROOT/CLAUDE.md"; then
    safe_remove "$PROJECT_ROOT/CLAUDE.md"
fi

# Remove AGENTS.md (only if created by this skill)
if [ -f "$PROJECT_ROOT/AGENTS.md" ] && marker_match "$PROJECT_ROOT/AGENTS.md"; then
    safe_remove "$PROJECT_ROOT/AGENTS.md"
fi

# Remove opencode.json (only if created by this skill)
if [ -f "$PROJECT_ROOT/opencode.json" ] && marker_match "$PROJECT_ROOT/opencode.json"; then
    safe_remove "$PROJECT_ROOT/opencode.json"
fi

# Remove directory skeleton (created by this skill for all project types)
# 数据目录（收件箱/知识库/发件箱/工作台/工作法）含用户产出，删除前必须确认；
# .tmp 为临时目录（含 worktree），同样需确认
skeleton_dirs="收件箱 知识库 发件箱 工作台 工作法 .tmp"
skeleton_exists=""
for dir in $skeleton_dirs; do
    if [ -e "$PROJECT_ROOT/$dir" ]; then
        skeleton_exists="$skeleton_exists $dir"
    fi
done

if [ -n "$skeleton_exists" ]; then
    echo "⚠️  检测到目录骨架:$skeleton_exists"
    read -r -p "  这些目录可能包含项目产出与工作树，确认删除？[y/N] " confirm < /dev/tty
    case "$confirm" in
        y|Y|yes|YES)
            for dir in $skeleton_dirs; do
                safe_remove "$PROJECT_ROOT/$dir"
            done
            ;;
        *)
            echo "  ⏭️  跳过目录骨架删除，保留:$skeleton_exists"
            ;;
    esac
fi

echo "✅ 清理完成"
