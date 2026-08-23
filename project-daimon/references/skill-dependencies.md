# Skill 依赖关系配置

本文件定义 Skill 对 MCP 服务器的依赖关系。

## ui-ux-pro-max

**Skill**: UI/UX 设计专家

**必需的 MCP**:

- `context7` - 用于查询 UI/UX 库文档和设计系统组件

**说明**: ui-ux-pro-max 需要 context7 来获取 React、Vue、Next.js 等框架的最新文档和代码示例。

---

## notebooklm-skill

**Skill**: NotebookLM 集成

**必需的 MCP**:

- `notebooklm` - NotebookLM MCP 服务器

**可选的 MCP**:

- `deepwiki` - 用于增强 GitHub 仓库文档检索

**说明**: notebooklm-skill 必须配合 notebooklm MCP 服务器使用。

---

## anthropic

**Skill**: Anthropic 官方 skills

**必需的 MCP**: 无

**可选的 MCP**:

- `context7` - 用于增强代码示例查询
- `deepwiki` - 用于查询开源项目实践

**说明**: anthropic skills 可以独立工作，但配合 MCP 服务器效果更好。
