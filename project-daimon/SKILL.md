---
name: project-daimon
description: 自动化项目初始化脚手架。用于新项目初始化时自动执行标准设置流程：Git 仓库初始化、.gitignore 配置、Agent 运行环境多选（Universal/Claude Code/Kimi desktop）、AGENTS.md 生成（卡帕西原则）、通过 /skillshare 启用 skill（中央库模式）、通过 mcp-bridge 渲染搜索 MCP（tavily/anysearch/exa/deepwiki）、项目类型模板配置。在用户开始新项目、创建空目录并准备初始化、或明确表示"初始化项目"时触发此 skill。
---

# Project Daimon

项目初始化自动化脚手架，一次性完成所有标准设置。原 project-scaffold 的接任者。本 skill 通过 `/skillshare`（嘴炮智能体）安装并管理 skill，通过内置 mcp-bridge 管理 MCP。

## 初始化流程

### 第一步：检查是否已初始化

在开始初始化前，先检查项目是否已经初始化：

```bash
scripts/check_initialized.sh <project-root>
```

**检查条件：**

- 存在 `.git/` 目录
- 或存在 `.claude/` 目录
- 或存在 `.opencode/` 目录
- 或存在 `.gitignore` 文件（包含 skill 标记）

**如果已初始化：**
询问用户如何处理：

- **重新初始化（合并配置）** → 执行合并脚本，将 skill 配置合并到现有配置
- **完全重置（删除重建）** → 执行清理脚本，删除所有 skill 产生的文件，然后重新初始化
- **取消** → 退出，保持现有配置

**合并脚本（推荐）：**

```bash
scripts/merge_scaffold_config.sh <project-root>
```

**清理脚本（完全重置）：**

```bash
scripts/cleanup_scaffold.sh <project-root>
```

### 第二步：一次性询问配置

使用 `AskUserQuestion` 一次性询问所有配置选项。

#### 一次性询问（必选）

```text
请选择 Agent 运行环境（可多选，至少选一项）：
☐ Universal：codex、OpenCode、kimi Cli（可全选）
☐ Claude Code
☐ Kimi desktop

AGENTS.md 工作原则？
○ 是 - 卡帕西原则（Spec→Verifier→Agent）+ skill 安装原则
○ 否

通过 /skillshare 启用哪些 skill？
☐ skillshare（控制类，默认选中）
☐ ui-ux-pro-max
☐ anthropic
☐ todo-workflow
☐ notebooklm-skill
☐ 暂不配置

启用哪些搜索 MCP？（通过 mcp-bridge 渲染）
☐ tavily
☐ anysearch
☐ exa
☐ deepwiki
☐ 暂不配置

请选择项目类型：
○ 方案研究 - 文档研究和资料收集
○ 前端开发 - React/Vue/Next.js
○ 后端开发 - Node.js/Python/Go
○ 全栈开发 - 完整应用
○ 通用项目 - 不限类型

AI复利工程？
○ 是 - 包含 TODO.md（任务记录）、经验.md（经验复用）
○ 否

Markdown美化工具？
○ 是 - 包含 Markdown lint（文档格式修复）、VSCode 扩展推荐
○ 否

AI修改后自动留痕？
○ 是 - 自动 git commit
○ 否

TODO 工作流？
○ 是 - 安装 todo-workflow Skill 和 TODO.md 模板
○ 否
```

### 第三步：执行初始化

根据用户选择，按顺序执行以下步骤：

#### 0. 前置依赖检查

如果用户选择了任何新选项（Agent 环境 / skill / MCP），检查 skillshare CLI：

```bash
skillshare --version
```

若失败，提示用户访问 https://github.com/runkids/skillshare 安装，终止初始化。

检查中央库：

```bash
test -d ~/.skills-src || echo "请先执行 skillshare init"
```

检查运行时依赖（如 Node.js、Python 版本）：

```bash
python3 scripts/check_dependencies.py
```

> 此脚本检测 MCP 运行所需依赖（如 anysearch 需要 Node.js 18+，notebooklm 需要 Python 3.10+），缺失时给出明确提示而非静默失败。

#### 0.5. /skillshare 安装 skillshare 控制 skill

通过 `/skillshare` 确保 `skillshare` 控制 skill 已安装到中央库：

```bash
skillshare install https://github.com/runkids/skillshare -g --skill skillshare
```

#### 1. Git 仓库初始化

```bash
scripts/init_git.sh
```

#### 2. 创建 .gitignore

```bash
cp assets/gitignore-template .gitignore
```

#### 3. 创建项目文档（可选）

**如果用户选择"AI复利工程？= 是"：**

```bash
# TODO.md - 任务跟踪文件
cp assets/TODO.md.template TODO.md

# 经验.md - 经验记录文件
cp assets/经验.md.template 经验.md
```

#### 3.5 初始化 AGENTS.md（可选）

**如果用户选择"AGENTS.md？= 是"：**

```bash
cp assets/AGENTS.md.template AGENTS.md
```

#### 4. 创建开发工具配置（可选）

**如果用户选择"Markdown美化工具？= 是"：**

```bash
# Markdown lint 配置
cp assets/.markdownlint.template .markdownlint.json

# VSCode 推荐扩展
mkdir -p .vscode
cp assets/.vscode.extensions.template .vscode/extensions.json
```

#### 4.5. 安装 TODO 工作流 Skill（可选）

**如果用户选择"TODO 工作流？= 是"：**

将 `todo-workflow` 作为 skillshare 中央库 skill 安装（与其他 skill 同样的软链分发方式）：

```bash
# 安装到中央库（与 skillshare/project-daimon 同级）
mkdir -p ~/.skills-src/todo-workflow
cp assets/todo-workflow.SKILL.md.template ~/.skills-src/todo-workflow/SKILL.md

# 加入项目 include 白名单（由 setup_skillshare.py 合并处理）
# 执行 skillshare sync -p 后以同样机制分发到所有 Agent 环境
```

```bash
# 复制 TODO.md 模板（如果 AI复利工程 未选择）
cp assets/TODO.md.template TODO.md
```

#### 5. 创建 Agent 运行环境结构

根据用户选择的 Agent 运行环境，分别创建对应的目录结构：

**如果选择了 Universal（codex / OpenCode / kimi Cli）：**

```bash
mkdir -p .opencode/skills
mkdir -p .opencode/plugin
mkdir -p .opencode/command
mkdir -p .agents/skills
# aspirations IDE 支持：.opencode → .aspirecode 软链
mkdir -p .aspirecode && ln -sfn .aspirecode .opencode
```

**如果选择了 Claude Code：**

```bash
scripts/create_claude_structure.sh <project-root> "$USER_SELECTED_MCPS"
```

**如果选择了 Kimi desktop：**

<!-- Kimi Desktop 配置走沙箱路径，由 mcp-bridge 处理 -->

**如果多选：** 多个环境的结构都创建。

#### 6. 配置项目类型模板

根据用户选择的项目类型，从 [references/project-templates.md](references/project-templates.md) 读取配置：

```bash
scripts/apply_project_template.py <project-root> <project-type>
```

模板配置包括：

- 项目特定的 MCP 服务器
- 需要安装的 Skills/Plugins
- 项目特定的配置文件

**模板数据流连接**：捕获模板推荐的 MCP/Skill 并与用户手动选择合并。

```bash
# 捕获模板输出并解析 JSON
TEMPLATE_OUTPUT=$(python3 scripts/apply_project_template.py <project-root> <project-type>)
TEMPLATE_MCPS=$(echo "$TEMPLATE_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(','.join(data.get('mcp_servers', [])))
")
TEMPLATE_SKILLS=$(echo "$TEMPLATE_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(','.join(data.get('claude_skills', [])))
")

# 与用户手动选择的 MCP 做并集合并
MERGED_MCPS=$(python3 -c "
user = set('$USER_SELECTED_MCPS'.split(','))
template = set('$TEMPLATE_MCPS'.split(','))
# 仅在 ALL_MCP_SERVERS 中存在的条目才保留
print(','.join(sorted(user | template)))
")

# 与用户手动选择的 Skills 做并集合并
MERGED_SKILLS=$(python3 -c "
user = set('$USER_SELECTED_SKILLS'.split(','))
template = set('$TEMPLATE_SKILLS'.split(','))
print(','.join(sorted(user | template)))
")
```

> 合并后的 `MERGED_MCPS` 和 `MERGED_SKILLS` 传递给后续步驟 6.5 和 7。

#### 6.5. 通过 skillshare 安装 Skills（可选）

**如果 `MERGED_SKILLS` 非空（不含"暂不配置"）：**

```bash
python3 scripts/setup_skillshare.py <project-root> <agent-envs> "$MERGED_SKILLS" [--dry-run]
```

脚本会自动：
1. 生成/更新 `.skillshare/config.yaml`，`sources.skills` 指向 `~/.skills-src`
2. 为每个 Agent 环境的 target 配置 `include` 白名单
3. 执行 `skillshare sync -p` 软链 skill 到各 Agent 目录

#### 7. 通过 mcp-bridge 渲染 MCP 服务器（可选）

**如果用户在"启用哪些搜索 MCP"中选择了 MCP（不含"暂不配置"）：**

```bash
python3 scripts/setup_mcp.py <project-root> --mcps <mcp-list> [--dry-run]
```

脚本会自动：
1. 生成 `.skillshare/mcp-bridge/servers.yaml`
2. 调用 `mcp-bridge.py sync` 渲染到各 Agent 环境
3. 更新 `.env.example` 含对应环境变量占位

#### 8. 安装 Marketplace 插件

```bash
scripts/install_plugins.py <project-root> <tools> <project-type>
```

#### 9. 配置自动 commit Hook（可选）

**如果用户选择"AI修改后自动留痕？= 是"：**

**Claude Code:** 在 `CLAUDE.md` 中添加 hook 指令
**OpenCode:** 配置 plugin 监听文件变化

```bash
scripts/setup_commit_hook.sh <project-root> <tools>
```

#### 10. 首次提交

```bash
git add .
git commit -m "初始化项目脚手架

- 创建 Git 仓库
- 添加 .gitignore
- 配置 [工具列表] 结构
- 配置 MCP 服务器（项目本地）
- 安装插件
- 配置自动 commit hook"
```

## 项目类型模板

项目类型模板定义在 [references/project-templates.md](references/project-templates.md)。

### 方案研究

**用途：** 需要大量文档研究和资料收集的项目

**配置：**

- MCP: deepwiki, notebooklm, exa
- Skills: notebooklm-skill
- 特点: 强大的文档检索和 AI 笔记能力

### 前端开发

**用途：** React/Vue/Next.js 等 Web 前端项目

**配置：**

- MCP: context7
- Skills: ui-ux-pro-max
- 特点: UI/UX 设计和组件开发支持

### 后端开发

**用途：** Node.js/Python/Go 等后端服务

**配置：**

- MCP: context7
- Skills: anthropic
- 特点: API 设计和架构支持

### 全栈开发

**用途：** 包含前后端的完整应用

**配置：**

- MCP: deepwiki, context7
- Skills: anthropic, ui-ux-pro-max
- 特点: 完整的全栈开发支持

### 通用项目

**用途：** 不限制类型的项目

**配置：**

- MCP: deepwiki, context7, exa
- Skills: 无特定 skill
- 特点: 通用开发支持

## 核心约定

初始化后的项目遵循以下约定：

1. **中文沟通**: 所有 commit 消息、代码注释、文档使用中文
2. **Markdown 自动提交**: 如果启用 hook，任何 .md 文件修改后立即 `git commit`
3. **项目级 skill 安装**：skills 通过 /skillshare 安装到中央库 `~/.skills-src/`，项目级通过 `.skillshare/config.yaml` include 白名单启用，`skillshare sync -p` 软链生效。
4. **代码格式化**: 使用 IDE 自带的 lint 和格式化工具
   - Markdown 文件：使用 `.markdownlint.json` 配置规则
   - 代码文件：使用项目配置的 linter（ESLint, Pylint 等）
   - AI 不应专注于格式调整，应专注于功能实现

## 开发工具配置对比

| 配置项 | Claude Code | OpenCode |
|--------|-------------|----------|
| 配置文件 | `CLAUDE.md`（项目根目录） | `opencode.json` |
| 技能目录 | `.claude/skills/` | `.opencode/plugin/` |
| 扩展目录 | - | `.opencode/agent/` |
| 命令目录 | - | `.opencode/command/` |
| MCP 配置 | `.mcp.json`（项目根目录） | `opencode.json` → `mcp` |
| Hook 配置 | `CLAUDE.md` 中添加指令 | plugin 监听文件 |

## 资源文件

### scripts/

- `check_initialized.sh`: 检查项目是否已初始化
- `cleanup_scaffold.sh`: 清理 skill 产生的文件（回溯版本用）
- `merge_scaffold_config.sh`: 合并 skill 配置到现有项目（非破坏性）
- `init_git.sh`: Git 仓库初始化脚本
- `setup_skillshare.py`: 生成/更新 `.skillshare/config.yaml` 并调用 `skillshare sync -p`
- `setup_mcp.py`: 生成 `.skillshare/mcp-bridge/servers.yaml` 并调用 `mcp-bridge.py sync`
- `mcp-bridge.py`: MCP 多 agent 渲染器（内置，无需用户单独安装）
- `create_claude_structure.sh`: Claude Code 目录结构创建脚本
- `create_opencode_structure.sh`: OpenCode 目录结构创建脚本
- `install_plugins.py`: Marketplace 插件安装脚本
- `apply_project_template.py`: 项目类型模板应用脚本
- `setup_commit_hook.sh`: 自动 commit hook 配置脚本

### assets/

- `AGENTS.md.template`: AGENTS.md 模板（卡帕西原则 + skill 安装原则）
- `gitignore-template`: 通用 .gitignore 模板
- `CLAUDE.md.template`: Claude Code CLAUDE.md 内容模板
- `opencode.json.template`: OpenCode 配置模板
- `TODO.md.template`: TODO 任务跟踪文件模板
- `经验.md.template`: 经验总结文档模板
- `.markdownlint.template`: Markdown lint 规则配置模板
- `.vscode.extensions.template`: VSCode 推荐扩展配置模板

### references/

- `mcp-servers.md`: MCP 服务器详细配置说明
- `marketplace.md`: Marketplace 插件配置列表
- `project-templates.md`: 项目类型模板配置

## 自定义

- **修改项目类型模板**: 编辑 `references/project-templates.md`
- **修改 Marketplace 列表**: 编辑 `references/marketplace.md`
- **修改 MCP 服务器**: 编辑 `scripts/setup_mcp.py` 中的 MCP 条目或 `.skillshare/mcp-bridge/servers.yaml`
- **修改 AGENTS.md**: 编辑 `assets/AGENTS.md.template`
- **修改 .gitignore**: 编辑 `assets/gitignore-template`
- **修改 Claude Code 模板**: 编辑 `assets/CLAUDE.md.template`
- **修改 OpenCode 模板**: 编辑 `assets/opencode.json.template`
- **修改 Markdown lint 规则**: 编辑 `assets/.markdownlint.template`
- **修改 VSCode 扩展推荐**: 编辑 `assets/.vscode.extensions.template`
