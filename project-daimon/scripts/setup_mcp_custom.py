#!/usr/bin/env python3
"""
[DEPRECATED] Setup MCP servers for custom configuration mode.
Use setup_mcp.py instead — all MCP definitions have been unified into
setup_mcp.py:ALL_MCP_SERVERS (including context7, notebooklm).

This file is kept for backward compatibility. All new MCP additions
should go to setup_mcp.py.
"""
# ⚠️ DEPRECATED — see setup_mcp.py for current MCP definitions

import os
import sys
import json
from pathlib import Path

# 复用 ALL_MCP_SERVERS 配置（从 setup_mcp.py）
ALL_MCP_SERVERS = {
    "deepwiki": {
        "type": "http",
        "url": "https://mcp.deepwiki.com/mcp",
        "headers": {}
    },
    "context7": {
        "type": "http",
        "url": "https://mcp.context7.com/mcp",
        "headers": {
            "CONTEXT7_API_KEY": ""
        }
    },
    "exa": {
        "type": "http",
        "url": "https://mcp.exa.ai/mcp",
        "headers": {}
    },
    "notebooklm": {
        "type": "http",
        "url": "https://notebooklm.mcp.server.url",
        "headers": {
            "GOOGLE_API_KEY": "",
            "GOOGLE_CLOUD_PROJECT": ""
        }
    },
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        "env": {}
    },
    "postgres": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:password@localhost:5432/db"],
        "env": {}
    },
    "brave-search": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {
            "BRAVE_API_KEY": ""
        }
    }
}

def setup_claude_mcp(project_path: Path, mcp_list: list):
    """Setup MCP for Claude Code (project-local)."""
    config_path = project_path / ".mcp.json"

    # Create MCP configuration
    mcp_config = {"mcpServers": {}}

    for server_name in mcp_list:
        if server_name in ALL_MCP_SERVERS:
            mcp_config["mcpServers"][server_name] = ALL_MCP_SERVERS[server_name]

    # Write MCP configuration
    with open(config_path, "w") as f:
        json.dump(mcp_config, f, indent=2)

    print(f"✅ MCP configuration written to {config_path}")
    return config_path

def setup_opencode_mcp(project_path: Path, mcp_list: list):
    """Setup MCP for OpenCode (project-local)."""
    config_path = project_path / "opencode.json"

    # Create or update opencode.json
    if config_path.exists():
        with open(config_path, "r") as f:
            opencode_config = json.load(f)
    else:
        opencode_config = {
            "env": {"LANGUAGE": "zh-CN"},
            "mcp": {}
        }

    # Add MCP servers
    for server_name in mcp_list:
        if server_name in ALL_MCP_SERVERS:
            server = ALL_MCP_SERVERS[server_name]
            if server.get("type") == "http":
                server_config = {"type": server["type"], "url": server["url"]}
                if server.get("headers"):
                    server_config["headers"] = server["headers"]
            else:
                server_config = {"command": server["command"], "args": server["args"]}
                if server.get("env"):
                    server_config["env"] = server["env"]
            opencode_config["mcp"][server_name] = server_config

    # Write configuration
    with open(config_path, "w") as f:
        json.dump(opencode_config, f, indent=2)

    print(f"✅ OpenCode MCP configuration written to {config_path}")
    return config_path

def main():
    """Main entry point."""
    if len(sys.argv) < 4:
        print("Usage: setup_mcp_custom.py <project-root> <tools> <mcp-list>")
        print("  tools: claude | opencode | claude,opencode")
        print("  mcp-list: comma-separated MCP server names")
        sys.exit(1)

    project_path = Path(sys.argv[1])
    tools = sys.argv[2].lower()
    mcp_list = sys.argv[3].split(',')

    print(f"🔧 Setting up MCP for custom configuration")
    print(f"   MCP servers: {', '.join(mcp_list)}")
    print(f"   Tools: {tools}")

    has_claude = "claude" in tools
    has_opencode = "opencode" in tools

    if has_claude:
        setup_claude_mcp(project_path, mcp_list)

    if has_opencode:
        setup_opencode_mcp(project_path, mcp_list)

if __name__ == "__main__":
    main()
