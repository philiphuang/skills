# Marketplace 插件配置

此文件定义从 marketplace 安装的插件列表。

## 格式说明

每个部分以 `### tool-type:project-type` 开头，下面列出需要安装的插件：

- `plugin-name: 描述说明 [来源]`

---

## 共享插件索引

以下插件被多个项目类型共享（列出所有可用插件）：

### Claude Skills

| 插件名称 | 适用的项目类型 | 说明 |
|:-------|:-------------|:-----|
| ui-ux-pro-max | frontend, fullstack | UI/UX 设计专家 [依赖: context7] |
| anthropic | backend, fullstack | Anthropic 官方 skills 集合 |
| prompt-optimizer | generic | Prompt 工程专家，57 种验证框架 |
| sync-skills | generic | 自动同步 skills 到多工具目录 |
| notebooklm-skill | research | NotebookLM 集成 |

### OpenCode Plugins

| 插件名称 | 适用的项目类型 | 说明 |
|:-------|:-------------|:-----|
| @opencode/typescript | frontend, fullstack | TypeScript 语言支持 |
| @opencode/eslint | frontend, fullstack | ESLint 集成 |
| @opencode/python | backend, fullstack | Python 语言支持 |
| @opencode/go | backend, fullstack | Go 语言支持 |

---

## Claude Code Skills

### claude:research

- `notebooklm-skill: NotebookLM 集成，用于文档分析和笔记管理 [依赖: notebooklm] [https://github.com/PleasePrompto/notebooklm-skill]`

### claude:frontend

- `ui-ux-pro-max: UI/UX 设计专家，提供设计和组件开发支持 [依赖: context7] [https://github.com/nextlevelbuilder/ui-ux-pro-max-skill]`

### claude:backend

- `anthropic: Anthropic 官方 skills 集合 [无强制依赖] [https://github.com/anthropics/skills]`

### claude:fullstack

- `ui-ux-pro-max: UI/UX 设计专家 [依赖: context7] [https://github.com/nextlevelbuilder/ui-ux-pro-max-skill]`
- `anthropic: Anthropic 官方 skills [无强制依赖] [https://github.com/anthropics/skills]`

### claude:generic

- `prompt-optimizer: Prompt 工程专家，使用 57 种经过验证的框架帮助用户创建优化的提示 [https://github.com/chujianyun/skills]`
- `sync-skills: 自动同步多个来源的 skills 到所有安装的 AI 编码工具目录（Claude Code、Cursor、Windsurf 等） [https://github.com/chujianyun/skills]`

---

## OpenCode Plugins

### opencode:generic

无默认 plugins

### opencode:frontend

- `@opencode/typescript: TypeScript 语言支持`
- `@opencode/eslint: ESLint 集成`

### opencode:backend

- `@opencode/python: Python 语言支持`
- `@opencode/go: Go 语言支持`

### opencode:fullstack

- `@opencode/typescript: TypeScript 语言支持`
- `@opencode/eslint: ESLint 集成`
