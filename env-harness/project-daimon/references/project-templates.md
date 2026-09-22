# 项目类型模板配置

此文件定义不同项目类型的 MCP 服务器、Skills 和配置。

> **工作法（所有项目类型通用）**：`工作法/` 目录骨架对所有项目类型都建，初始化即创建。
> 工作法 = 治理项目产出的方法文档，先于项目存在、持续迭代、跨项目复用；
> 研究/业务流程沉淀为工作法（如 `需求调研工作法.md`），产出（收件箱/知识库/发件箱/工作台）受工作法管理。
> 详见 AGENTS.md「工作法」章节（文件清单仅为举例，非强制）。

## 格式说明

每个项目类型包含：

- `description`: 项目描述
- `mcp_servers`: 需要的 MCP 服务器列表
- `claude_skills`: Claude Code skills 列表
- `opencode_plugins`: OpenCode plugins 列表

---

## 方案研究 (research)

**用途：** 需要大量文档研究和资料收集的项目

**配置：**

- MCP 服务器: deepwiki, notebooklm, exa
- Claude Skills: 无特定 skill
- OpenCode Plugins: 无

**特点：** 强大的文档检索和 AI 笔记能力

---

## 前端开发 (frontend)

**用途：** React/Vue/Next.js 等 Web 前端项目

**配置：**

- MCP 服务器: context7
- Claude Skills: ui-ux-pro-max
- OpenCode Plugins: @opencode/typescript, @opencode/eslint

**特点：** UI/UX 设计和组件开发支持

---

## 后端开发 (backend)

**用途：** Node.js/Python/Go 等后端服务

**配置：**

- MCP 服务器: context7
- Claude Skills: 无特定 skill
- OpenCode Plugins: 根据语言类型选择

**特点：** API 设计和架构支持

---

## 全栈开发 (fullstack)

**用途：** 包含前后端的完整应用

**配置：**

- MCP 服务器: deepwiki, context7
- Claude Skills: ui-ux-pro-max
- OpenCode Plugins: @opencode/typescript, @opencode/eslint

**特点：** 完整的全栈开发支持

---

## 通用项目 (generic)

**用途：** 不限制类型的项目

**配置：**

- MCP 服务器: deepwiki, context7, exa
- Claude Skills: 无特定 skill
- OpenCode Plugins: 无

**特点：** 通用开发支持
