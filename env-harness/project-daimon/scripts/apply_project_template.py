#!/usr/bin/env python3
"""
Apply project type template configuration.
Reads template from project-templates.md and configures MCP/skills accordingly.
"""

import sys
import re
from pathlib import Path

PROJECT_TEMPLATES = {
    "research": {
        "description": "方案研究 - 文档研究和资料收集",
        "mcp_servers": ["deepwiki", "notebooklm", "exa"],
        "claude_skills": ["notebooklm-skill"],
        "opencode_plugins": []
    },
    "frontend": {
        "description": "前端开发 - React/Vue/Next.js",
        "mcp_servers": ["context7"],
        "claude_skills": ["ui-ux-pro-max"],
        "opencode_plugins": ["@opencode/typescript", "@opencode/eslint"]
    },
    "backend": {
        "description": "后端开发 - Node.js/Python/Go",
        "mcp_servers": ["context7"],
        "claude_skills": ["anthropic"],
        "opencode_plugins": []
    },
    "fullstack": {
        "description": "全栈开发 - 完整应用",
        "mcp_servers": ["deepwiki", "context7"],
        "claude_skills": ["anthropic", "ui-ux-pro-max"],
        "opencode_plugins": ["@opencode/typescript", "@opencode/eslint"]
    },
    "generic": {
        "description": "通用项目",
        "mcp_servers": ["deepwiki", "context7", "exa"],
        "claude_skills": [],
        "opencode_plugins": []
    }
}

def get_template(project_type: str):
    """Get template configuration for project type."""
    return PROJECT_TEMPLATES.get(project_type, PROJECT_TEMPLATES["generic"])

def main():
    if len(sys.argv) < 3:
        print("Usage: apply_project_template.py <project-root> <project-type>")
        print("  project-type: research | frontend | backend | fullstack | generic")
        sys.exit(1)

    project_root = Path(sys.argv[1])
    project_type = sys.argv[2]

    template = get_template(project_type)

    print(f"📋 Applying template: {template['description']}")
    print(f"   MCP servers: {', '.join(template['mcp_servers'])}")
    print(f"   Claude skills: {', '.join(template['claude_skills']) or 'None'}")
    print(f"   OpenCode plugins: {', '.join(template['opencode_plugins']) or 'None'}")

    # Return template info as JSON for other scripts to use
    import json
    print(json.dumps(template, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
