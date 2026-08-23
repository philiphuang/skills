#!/usr/bin/env python3
"""
依赖环境检查和自动安装模块
支持检测 Python、Node.js、uv、npm、Git 等运行时环境
"""

import sys
import subprocess
import platform
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class DependencyChecker:
    """依赖检查器 - 检测系统依赖并提供安装建议"""

    # 依赖定义（从 MCP/Skills 配置中派生）
    DEPENDENCIES = {
        "python": {
            "name": "Python",
            "min_version": "3.10",
            "check_command": "python3 --version",
            "version_parser": lambda out: out.split()[1],
            "install": {
                "macos": "brew install python@3.11",
                "linux": "sudo apt install python3.11",
                "windows": "https://www.python.org/downloads/"
            }
        },
        "node": {
            "name": "Node.js",
            "min_version": "18.0",
            "check_command": "node --version",
            "version_parser": lambda out: out.lstrip('v'),
            "install": {
                "macos": "brew install node",
                "linux": "curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt install -y nodejs",
                "windows": "https://nodejs.org/"
            }
        },
        "npm": {
            "name": "npm",
            "min_version": "9.0",
            "check_command": "npm --version",
            "version_parser": lambda out: out,
            "depends_on": ["node"]
        },
        "uv": {
            "name": "uv",
            "min_version": "0.1",
            "check_command": "uv --version",
            "version_parser": lambda out: out.split()[1] if len(out.split()) > 1 else out,
            "install": {
                "macos": "curl -LsSf https://astral.sh/uv/install.sh | sh",
                "linux": "curl -LsSf https://astral.sh/uv/install.sh | sh",
                "windows": "powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""
            }
        },
        "git": {
            "name": "Git",
            "min_version": "2.0",
            "check_command": "git --version",
            "version_parser": lambda out: out.split()[2],
            "install": {
                "macos": "brew install git",
                "linux": "sudo apt install git",
                "windows": "https://git-scm.com/downloads"
            }
        }
    }

    # MCP/Skills 依赖映射
    MCP_DEPENDENCIES = {
        "notebooklm": ["python"],
        "filesystem": ["node"],
        "context7": [],  # HTTP 模式，无需本地依赖
        "deepwiki": [],
        "exa": [],
        "postgres": [],
        "brave-search": []
    }

    SKILL_DEPENDENCIES = {
        "notebooklm-skill": ["python"],
        "ui-ux-pro-max": [],
        "anthropic": []
    }

    def __init__(self, mcp_servers: List[str] = None, skills: List[str] = None):
        self.mcp_servers = mcp_servers or []
        self.skills = skills or []
        self.platform = self._detect_platform()

    def _detect_platform(self) -> str:
        """检测操作系统平台"""
        system = platform.system().lower()
        if system == "darwin":
            return "macos"
        elif system == "windows":
            return "windows"
        return "linux"

    def check_command_exists(self, command: str) -> bool:
        """检查命令是否存在"""
        try:
            subprocess.run(
                ["which", command] if self.platform != "windows" else ["where", command],
                capture_output=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def check_version(self, dep_name: str) -> Tuple[bool, Optional[str]]:
        """检查依赖版本是否满足要求"""
        dep = self.DEPENDENCIES.get(dep_name)
        if not dep:
            return False, None

        try:
            result = subprocess.run(
                dep["check_command"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                return False, None

            version = dep["version_parser"](result.stdout.strip())
            return self._compare_versions(version, dep["min_version"]), version
        except Exception:
            return False, None

    def _compare_versions(self, current: str, required: str) -> bool:
        """比较版本号"""
        try:
            current_parts = [int(x) for x in current.split(".")[:2]]
            required_parts = [int(x) for x in required.split(".")[:2]]
            return current_parts >= required_parts
        except (ValueError, IndexError):
            return False

    def get_required_dependencies(self) -> List[str]:
        """根据选定的 MCP/Skills 获取所需依赖"""
        required = set()

        for mcp in self.mcp_servers:
            required.update(self.MCP_DEPENDENCIES.get(mcp, []))

        for skill in self.skills:
            required.update(self.SKILL_DEPENDENCIES.get(skill, []))

        # 检查传递依赖
        all_deps = set(required)
        for dep in list(required):
            all_deps.update(self.DEPENDENCIES.get(dep, {}).get("depends_on", []))

        return sorted(all_deps)

    def check_all(self) -> Dict[str, Dict]:
        """检查所有必需的依赖"""
        required = self.get_required_dependencies()
        results = {}

        for dep_name in required:
            exists = self.check_command_exists(dep_name)
            version_ok, version = self.check_version(dep_name) if exists else (False, None)

            results[dep_name] = {
                "exists": exists,
                "version": version,
                "satisfied": version_ok,
                "install_command": self.DEPENDENCIES[dep_name]["install"].get(self.platform)
            }

        return results

    def print_report(self, results: Dict[str, Dict]) -> bool:
        """打印依赖检查报告"""
        print("\n📋 依赖环境检查报告")
        print("=" * 50)

        all_ok = True
        for dep_name, info in results.items():
            dep_info = self.DEPENDENCIES[dep_name]
            name = dep_info["name"]

            if info["satisfied"]:
                print(f"✅ {name}: {info['version']}")
            elif info["exists"]:
                print(f"⚠️  {name}: 版本过低 ({info['version']} < {dep_info['min_version']})")
                all_ok = False
            else:
                print(f"❌ {name}: 未安装")
                print(f"   安装命令: {info['install_command']}")
                all_ok = False

        print("=" * 50)
        return all_ok

    def auto_install(self, dep_name: str) -> bool:
        """自动安装依赖（需用户确认）"""
        dep_info = self.DEPENDENCIES.get(dep_name)
        if not dep_info:
            return False

        install_cmd = dep_info["install"].get(self.platform)
        if not install_cmd:
            print(f"❌ {dep_name}: 不支持当前平台的自动安装")
            return False

        # 如果是 URL，提示用户手动安装
        if install_cmd.startswith("http"):
            print(f"\n📦 请手动安装 {dep_info['name']}")
            print(f"   访问: {install_cmd}")
            return False

        print(f"\n📦 正在安装 {dep_info['name']}...")
        print(f"命令: {install_cmd}")

        try:
            subprocess.run(install_cmd, shell=True, check=True)
            print(f"✅ {dep_info['name']} 安装成功")
            return True
        except subprocess.CalledProcessError:
            print(f"❌ {dep_info['name']} 安装失败")
            return False


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="检查项目依赖环境")
    parser.add_argument("--mcp", nargs="+", help="MCP 服务器列表")
    parser.add_argument("--skills", nargs="+", help="Skills 列表")
    parser.add_argument("--auto-install", action="store_true", help="自动安装缺失依赖")

    args = parser.parse_args()

    checker = DependencyChecker(mcp_servers=args.mcp, skills=args.skills)
    results = checker.check_all()
    all_ok = checker.print_report(results)

    if not all_ok:
        if args.auto_install:
            for dep_name, info in results.items():
                if not info["satisfied"]:
                    checker.auto_install(dep_name)
        else:
            print("\n⚠️  请手动安装缺失的依赖后重试")
            sys.exit(1)


if __name__ == "__main__":
    main()
