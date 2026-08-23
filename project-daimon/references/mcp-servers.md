# MCP 服务器配置参考

本项目配置以下 MCP 服务器：

## deepwiki

深度文档检索服务器，用于智能文档搜索和上下文理解。

- 类型：远程 HTTP MCP（Streamable HTTP）
- URL：`https://mcp.deepwiki.com/mcp`
- 无需 API Key，无需本地安装

## context7

上下文管理服务器，用于长期记忆和上下文保持。

- 安装：`npx @context7/mcp-server`
- 环境变量：`CONTEXT7_API_KEY`

## notebooklm

Google NotebookLM 集成，用于笔记管理和 AI 辅助文档处理。

- 安装：`npx @notebooklm/mcp-server`
- 环境变量：
  - `GOOGLE_API_KEY`
  - `GOOGLE_CLOUD_PROJECT`

## exa

AI 驱动的网络搜索服务器。

- 安装：`npx exa-mcp-server`
- 环境变量：`EXA_API_KEY`

## 环境变量设置

在 `~/.zshrc` 或 `~/.bashrc` 中添加：

```bash
# Context7
export CONTEXT7_API_KEY="your_key_here"

# NotebookLM
export GOOGLE_API_KEY="your_key_here"
export GOOGLE_CLOUD_PROJECT="your_project_id"

# Exa
export EXA_API_KEY="your_key_here"
```

然后执行 `source ~/.zshrc` 使其生效。
