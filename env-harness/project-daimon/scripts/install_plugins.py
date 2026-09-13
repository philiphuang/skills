#!/usr/bin/env python3
"""
Install plugins/skills from marketplace configuration.
Supports both Claude Code skills and OpenCode plugins.
"""

import sys
import json
import re
import subprocess
from pathlib import Path

def read_marketplace_config(skill_path: Path, tool_type: str, project_type: str):
    """Read marketplace configuration."""
    config_file = skill_path / "references" / "marketplace.md"

    if not config_file.exists():
        print(f"⚠️  Marketplace config not found: {config_file}")
        return []

    # Parse marketplace.md to extract plugin list
    # Format: ### tool-type:project-type
    #         - plugin-name: description [GitHub URL]
    content = config_file.read_text()
    section_marker = f"### {tool_type}:{project_type}"

    plugins = []
    in_section = False

    for line in content.split('\n'):
        if line.startswith(section_marker):
            in_section = True
            continue
        if in_section:
            if line.startswith('###'):
                break
            if line.strip().startswith('- '):
                plugin_line = line.strip()[2:].strip('`')
                # Parse: plugin-name: description [url]
                if ':' in plugin_line:
                    parts = plugin_line.split(':', 1)
                    name = parts[0].strip()
                    desc_part = parts[1].strip()

                    # Extract GitHub URL from description
                    # Supports formats: [url], (url), [text](url)
                    url_match = re.search(r'\[([^\]]+)\]\((https://github\.com/[^)]+)\)|\[(https://github\.com/[^]]+)\]|\((https://github\.com/[^)]+)\)', desc_part)
                    url = None
                    if url_match:
                        url = url_match.group(2) or url_match.group(3) or url_match.group(4)
                        # Remove URL from description for cleaner display
                        desc = re.sub(r'\s*\[[^\]]+\]\((?:https?:\/\/[^)]+)\)|\s*\[(?:https?:\/\/[^]]+)\]|\s*\((?:https?:\/\/[^)]+)\)', '', desc_part).strip()
                    else:
                        desc = desc_part

                    plugins.append((name, desc, url))

    return plugins

def run_command(cmd, cwd=None):
    """Run shell command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def clone_github_repo(url, dest_dir):
    """Clone a GitHub repository to destination directory."""
    # Check if git is available
    success, _, _ = run_command("git --version")
    if not success:
        print(f"  ⚠️  Git is not available, skipping {url}")
        return False

    # Check if destination already exists
    if dest_dir.exists():
        print(f"  ℹ️  Directory already exists: {dest_dir}")
        return True

    # Create parent directory
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
    """Check if a skill is already installed (has SKILL.md)."""
    return dest_dir.exists() and (dest_dir / "SKILL.md").exists()

def install_claude_skill(project_path: Path, skill_name: str, description: str, github_url: str):
    """Install Claude Code skill to project local skills directory."""
    skills_dir = project_path / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    if github_url:
        # Extract repo name from URL for directory name
        # e.g., https://github.com/PleasePrompto/notebooklm-skill -> notebooklm-skill
        repo_name = github_url.rstrip('/').split('/')[-1]
        dest_dir = skills_dir / repo_name

        # Check if already installed
        if is_skill_installed(dest_dir):
            print(f"  ⏭️  Already installed: {skill_name} → {dest_dir}")
            return

        success = clone_github_repo(github_url, dest_dir)

        if success:
            print(f"  📦 Installed: {skill_name} → {dest_dir}")
    else:
        # For skills without GitHub URL, create a placeholder
        skill_file = skills_dir / f"{skill_name}.md"
        skill_file.write_text(f"# {skill_name}\n\n{description}\n")
        print(f"  📦 Created placeholder: {skill_file}")

def is_plugin_installed(dest_dir: Path) -> bool:
    """Check if a plugin is already installed."""
    if not dest_dir.exists():
        return False
    # Check for common plugin files
    plugin_files = ['package.json', 'plugin.json', 'manifest.json', 'extension.ts']
    return any((dest_dir / f).exists() for f in plugin_files)

def install_opencode_plugin(project_path: Path, plugin_name: str, description: str, github_url: str):
    """Install OpenCode plugin to project local plugin directory."""
    plugin_dir = project_path / ".opencode" / "plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    if github_url:
        # Extract repo name from URL
        repo_name = github_url.rstrip('/').split('/')[-1]
        dest_dir = plugin_dir / repo_name

        # Check if already installed
        if is_plugin_installed(dest_dir):
            print(f"  ⏭️  Already installed: {plugin_name} → {dest_dir}")
            return

        success = clone_github_repo(github_url, dest_dir)

        if success:
            print(f"  📦 Installed plugin: {plugin_name} → {dest_dir}")
    else:
        # For plugins without GitHub URL, create a placeholder
        safe_name = plugin_name.replace('/', '-')
        plugin_file = plugin_dir / f"{safe_name}.json"
        plugin_file.parent.mkdir(parents=True, exist_ok=True)
        plugin_file.write_text(json.dumps({
            "name": plugin_name,
            "description": description
        }, indent=2))
        print(f"  📦 Created placeholder: {plugin_file}")

def install_dependencies(skills_dir: Path):
    """Install Python dependencies for skills that require them."""
    # Check for skills with requirements.txt or setup.py
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue

        # Check for notebooklm-skill specific setup
        if (skill_dir / "scripts" / "ask_question.py").exists():
            # Check if already set up (has .venv)
            venv_dir = skill_dir / ".venv"
            if venv_dir.exists():
                # Already set up, skip
                continue

            print(f"\n🔧 Setting up {skill_dir.name}...")

            # Create .venv directory
            if not venv_dir.exists():
                print(f"  📦 Creating virtual environment...")
                success, _, _ = run_command(f"python -m venv {venv_dir}")
                if success:
                    print(f"  ✅ Virtual environment created")
                else:
                    print(f"  ⚠️  Failed to create virtual environment")
                    continue

            # Install dependencies if requirements.txt exists
            requirements_file = skill_dir / "requirements.txt"
            if requirements_file.exists():
                # Determine pip path based on OS
                import platform
                if platform.system() == "Windows":
                    pip_path = venv_dir / "Scripts" / "pip"
                else:
                    pip_path = venv_dir / "bin" / "pip"

                print(f"  📦 Installing dependencies...")
                success, _, _ = run_command(f"{pip_path} install -r {requirements_file}")
                if success:
                    print(f"  ✅ Dependencies installed")
                else:
                    print(f"  ⚠️  Failed to install dependencies")

            # Create data directory
            data_dir = skill_dir / "data"
            data_dir.mkdir(exist_ok=True)
            (data_dir / "library.json").write_text("[]")
            (data_dir / "auth_info.json").write_text("{}")

def main():
    if len(sys.argv) < 4:
        print("Usage: install_plugins.py <project-root> <tool-type> <project-type>")
        print("  tool-type: claude | opencode")
        print("  project-type: generic | frontend | backend | fullstack | research")
        sys.exit(1)

    project_root = Path(sys.argv[1])
    tool_type = sys.argv[2]  # claude or opencode
    project_type = sys.argv[3]

    # Get skill path (assuming we're in the skill directory)
    skill_path = Path(__file__).parent.parent

    plugins = read_marketplace_config(skill_path, tool_type, project_type)

    if not plugins:
        print(f"⚠️  No plugins found for {tool_type}:{project_type}")
        return

    print(f"📦 Installing {len(plugins)} plugin(s) for {tool_type}:{project_type}...")

    for plugin_name, description, github_url in plugins:
        print(f"\n• {plugin_name}: {description}")
        if github_url:
            print(f"  URL: {github_url}")

        if tool_type == "claude":
            install_claude_skill(project_root, plugin_name, description, github_url)
        elif tool_type == "opencode":
            install_opencode_plugin(project_root, plugin_name, description, github_url)

    # Install dependencies for skills that need them
    if tool_type == "claude":
        skills_dir = project_root / ".claude" / "skills"
        if skills_dir.exists():
            install_dependencies(skills_dir)

    print("\n✅ Plugin installation complete")

if __name__ == "__main__":
    main()
