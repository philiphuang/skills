#!/usr/bin/env python3
"""
依赖验证模块
检查 Skill 对 MCP 的依赖关系，并自动添加缺失的依赖
"""

import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Skill 依赖关系配置
SKILL_DEPENDENCIES = {
    "ui-ux-pro-max": {
        "required_mcp": ["context7"],
        "optional_mcp": [],
        "description": "需要 context7 查询 UI/UX 库文档"
    },
    "notebooklm-skill": {
        "required_mcp": ["notebooklm"],
        "optional_mcp": ["deepwiki"],
        "description": "需要 notebooklm MCP 服务器"
    },
    "anthropic": {
        "required_mcp": [],
        "optional_mcp": ["context7", "deepwiki"],
        "description": "可选增强功能"
    }
}

class DependencyValidator:
    """依赖验证器"""

    def __init__(self, selected_mcp: Set[str], selected_skills: Set[str]):
        self.selected_mcp = selected_mcp
        self.selected_skills = selected_skills
        self.auto_added_mcp: Set[str] = set()

    def auto_add_dependencies(self) -> Set[str]:
        """自动添加已选择 Skill 的依赖"""
        for skill in self.selected_skills:
            if skill not in SKILL_DEPENDENCIES:
                continue

            deps = SKILL_DEPENDENCIES[skill]

            for required_mcp in deps["required_mcp"]:
                if required_mcp not in self.selected_mcp:
                    self.selected_mcp.add(required_mcp)
                    self.auto_added_mcp.add(required_mcp)

        return self.auto_added_mcp

    def get_dependency_summary(self) -> str:
        """生成依赖关系摘要"""
        lines = []

        if self.auto_added_mcp:
            lines.append("\n✅ 已自动添加依赖的 MCP 服务器：")
            for mcp in sorted(self.auto_added_mcp):
                lines.append(f"   - {mcp}")

        return "\n".join(lines) if lines else "无依赖需要自动添加"


def main():
    """命令行入口"""
    if len(sys.argv) < 3:
        print("Usage: validate_dependencies.py <mcp1,mcp2,...> <skill1,skill2,...>")
        sys.exit(1)

    selected_mcp = set(sys.argv[1].split(','))
    selected_skills = set(sys.argv[2].split(','))

    validator = DependencyValidator(selected_mcp, selected_skills)

    print("🔍 验证依赖关系...")

    auto_added = validator.auto_add_dependencies()
    if auto_added:
        print(f"\n✅ 自动添加依赖: {', '.join(auto_added)}")

    summary = validator.get_dependency_summary()
    print(summary)

    print(f"\n最终 MCP 列表: {', '.join(sorted(validator.selected_mcp))}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
