#!/usr/bin/env python3
"""
Install plugins/skills for custom configuration mode.
Supports user-specified skill and plugin lists.
"""

import sys
import re
import subprocess
from pathlib import Path
from typing import List, Tuple

# Skill/Plugin 仓库映射
SKILL_REPOS = {
    "ui-ux-pro-max": "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill",
    "anthropic": "https://github.com/anthropics/skills",
    "notebooklm-skill": "https://github.com/PleasePrompto/notebooklm-skill"
}

PLUGIN_REPOS = {
    "@opencode/typescript": "https://github.com/opencode/typescript-plugin",
    "@opencode/eslint": "https://github.com/opencode/eslint-plugin",
    "@opencode/python": "https://github.com/opencode/python-plugin",
    "@opencode/go": "https://github.com/opencode/go-plugin"
}

def run_command(cmd, cwd=None):
    """Run shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=300
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def clone_github_repo(url, dest_dir):
    """Clone a GitHub repository to destination directory."""
    if dest_dir.exists():
        print(f"  ℹ️  Directory already exists: {dest_dir}")
        return True

    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"  📥 Cloning from {url}...")

    success, stdout, stderr = run_command(f"git clone {url} {dest_dir}")

    if success:
        print(f"  ✅ Cloned to {dest_dir}")
        return True
    else:
        print(f"  ❌ Failed to clone: {stderr}")
        return False

def is_skill_installed(dest_dir: Path) -> bool:
    """Check if a skill is already installed."""
    return dest_dir.exists() and (dest_dir / "SKILL.md").exists()

def install_claude_skill(project_path: Path, skill_name: str):
    """Install Claude Code skill to project local skills directory."""
    if skill_name not in SKILL_REPOS:
        print(f"  ⚠️  Unknown skill: {skill_name}")
        return

    skills_dir = project_path / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    github_url = SKILL_REPOS[skill_name]
    repo_name = github_url.rstrip('/').split('/')[-1].replace('-skill', '').replace('-', '')
    dest_dir = skills_dir / repo_name

    if is_skill_installed(dest_dir):
        print(f"  ⏭️  Already installed: {skill_name}")
        return

    clone_github_repo(github_url, dest_dir)
    print(f"  📦 Installed: {skill_name}")

def install_opencode_plugin(project_path: Path, plugin_name: str):
    """Install OpenCode plugin to project local plugin directory."""
    if plugin_name not in PLUGIN_REPOS:
        print(f"  ⚠️  Unknown plugin: {plugin_name}")
        return

    plugin_dir = project_path / ".opencode" / "plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    github_url = PLUGIN_REPOS[plugin_name]
    repo_name = github_url.rstrip('/').split('/')[-1]
    dest_dir = plugin_dir / repo_name

    if dest_dir.exists():
        print(f"  ⏭️  Already installed: {plugin_name}")
        return

    clone_github_repo(github_url, dest_dir)
    print(f"  📦 Installed plugin: {plugin_name}")

def main():
    """Main entry point."""
    if len(sys.argv) < 4:
        print("Usage: install_plugins_custom.py <project-root> <tool-type> --skills <skill1,skill2,...> --plugins <plugin1,plugin2,...>")
        sys.exit(1)

    project_root = Path(sys.argv[1])
    tool_type = sys.argv[2]  # claude or opencode

    # Parse arguments
    skills = []
    plugins = []
    for i in range(3, len(sys.argv)):
        if sys.argv[i] == "--skills" and i + 1 < len(sys.argv):
            skills = sys.argv[i + 1].split(',')
        elif sys.argv[i] == "--plugins" and i + 1 < len(sys.argv):
            plugins = sys.argv[i + 1].split(',')

    if tool_type == "claude":
        print(f"📦 Installing {len(skills)} skill(s)...")
        for skill_name in skills:
            print(f"\n• {skill_name}")
            install_claude_skill(project_root, skill_name)

    elif tool_type == "opencode":
        print(f"📦 Installing {len(plugins)} plugin(s)...")
        for plugin_name in plugins:
            print(f"\n• {plugin_name}")
            install_opencode_plugin(project_root, plugin_name)

    print("\n✅ Plugin installation complete")

if __name__ == "__main__":
    main()
