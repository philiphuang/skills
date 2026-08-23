#!/usr/bin/env python3
"""
Generate/update .skillshare/config.yaml for a project-daimon initialized project.
Creates a config that links to a central skills source and defines per-agent targets
with include whitelists. Then calls `skillshare sync -p` to distribute skills.

Usage:
    setup_skillshare.py <project-root> <agent-envs> <include-list>
                        [--central-src <path>] [--dry-run] [--kimi-path <path>]

    agent-envs:   Comma-separated list: universal, claude, kimidesktop, all
    include-list: Comma-separated list of skill names to whitelist
    --central-src: Path to central skills source (default: ~/.skills-src)
    --dry-run:     Preview config without writing or syncing
    --kimi-path:   Custom path for Kimi Desktop skills directory
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Agent environment → target mapping
# ---------------------------------------------------------------------------
TARGET_MAP = {
    "universal": {
        "name": "universal",
        "path": "./.agents/skills",
    },
    "claude": {
        "name": "claude",
        "path": ".claude/skills",
    },
    "opencode": {
        "name": "opencode",
        "path": ".opencode/skills",   # → .aspirecode/skills via symlink
    },
    "kimidesktop": {
        "name": "kimidesktop",
        "path": None,  # User-specific, requires --kimi-path or default
    },
}

DEFAULT_KIMI_PATH = "~/Library/Application Support/Kimi/daimon-share/daimon/skills"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate .skillshare/config.yaml and sync skills"
    )
    parser.add_argument(
        "project_root", type=str, help="Project root directory"
    )
    parser.add_argument(
        "agent_envs", type=str,
        help="Comma-separated agent environments: universal, claude, kimidesktop, all"
    )
    parser.add_argument(
        "include_list", type=str,
        help="Comma-separated list of skill names to whitelist"
    )
    parser.add_argument(
        "--central-src", type=str, default="~/.skills-src",
        help="Path to central skills source (default: ~/.skills-src)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview config without writing or syncing"
    )
    parser.add_argument(
        "--kimi-path", type=str, default=None,
        help="Custom path for Kimi Desktop skills directory"
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def resolve_agents(agent_envs: str) -> list[str]:
    """Parse comma-separated agent-envs, expand 'all' to all known agents."""
    agents = [a.strip().lower() for a in agent_envs.split(",") if a.strip()]
    if "all" in agents:
        return list(TARGET_MAP.keys())
    # Filter unknown agents
    valid = [a for a in agents if a in TARGET_MAP]
    unknown = set(agents) - set(TARGET_MAP.keys())
    if unknown:
        print(f"⚠️  Unknown agents ignored: {', '.join(sorted(unknown))}")
        print(f"   Known: {', '.join(TARGET_MAP.keys())}")
    return valid


def build_target_entry(agent: str, kimi_path: str | None) -> dict | None:
    """Build a single target entry dict for the given agent."""
    tmpl = TARGET_MAP[agent]
    if agent == "kimidesktop":
        path = kimi_path or DEFAULT_KIMI_PATH
        if path is None:
            print(f"❌ Kimi Desktop requires --kimi-path or a default path")
            return None
        path = os.path.expanduser(path)  # Expand ~ in the path
    else:
        path = tmpl["path"]

    return {
        "name": tmpl["name"],
        "skills": {
            "path": path,
            "include": [],  # Filled in by caller after merging
        },
    }


def load_existing_config(project_root: Path) -> dict | None:
    """Load existing .skillshare/config.yaml if it exists. Returns None if absent."""
    config_file = project_root / ".skillshare" / "config.yaml"
    if not config_file.exists():
        return None

    try:
        import yaml
        with open(config_file, "r") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        print("⚠️  PyYAML not installed, cannot read existing config for merging.")
        print("   Install it: pip install pyyaml")
        return None
    except Exception as e:
        print(f"⚠️  Failed to read existing config: {e}")
        return None


def merge_include_lists(
    existing_targets: list[dict],
    new_targets: list[dict],
    include_list: list[str],
) -> list[dict]:
    """Merge include lists: existing + new includes, deduplicated."""
    # Build lookup from existing targets by name
    existing_by_name = {}
    for t in existing_targets:
        if isinstance(t, dict):
            existing_by_name[t.get("name", "")] = t
        elif isinstance(t, str):
            # Legacy short-form target (just a name string)
            existing_by_name[t] = {"name": t}

    merged = []
    for new_t in new_targets:
        name = new_t["name"]
        if name in existing_by_name:
            existing_t = existing_by_name[name]
            # Merge include lists
            existing_includes = set()
            if isinstance(existing_t, dict):
                skills_block = existing_t.get("skills", {})
                if isinstance(skills_block, dict):
                    existing_includes = set(skills_block.get("include", []))
            merged_includes = sorted(existing_includes | set(include_list))
            new_t["skills"]["include"] = merged_includes
        else:
            new_t["skills"]["include"] = list(include_list)

        merged.append(new_t)

    # Append any existing targets not in the new set
    new_names = {t["name"] for t in new_targets}
    for existing_t in existing_targets:
        name = existing_t.get("name") if isinstance(existing_t, dict) else existing_t
        if name not in new_names:
            merged.append(existing_t)

    return merged


def generate_yaml(config: dict) -> str:
    """Generate YAML string for the config dict."""
    try:
        import yaml
        return yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        # Fallback: simple manual YAML generation
        lines = []
        lines.append("# yaml-language-server: $schema=https://raw.githubusercontent.com/runkids/skillshare/main/schemas/project-config.schema.json")
        lines.append("sources:")
        lines.append(f"  skills: {config['sources']['skills']}")
        lines.append("targets:")
        for t in config["targets"]:
            lines.append(f"  - name: {t['name']}")
            skills = t.get("skills", {})
            lines.append(f"    skills:")
            lines.append(f"      path: {skills.get('path', '')}")
            lines.append(f"      include:")
            for item in skills.get("include", []):
                lines.append(f"        - {item}")
        return "\n".join(lines) + "\n"

    except Exception as e:
        print(f"❌ Failed to generate YAML: {e}")
        sys.exit(1)


def write_config(project_root: Path, config: dict, dry_run: bool):
    """Write config.yaml to .skillshare/ directory."""
    skillshare_dir = project_root / ".skillshare"
    config_file = skillshare_dir / "config.yaml"

    yaml_str = generate_yaml(config)

    if dry_run:
        print("\n📄 DRY-RUN — would write to:", config_file)
        print("---")
        print(yaml_str.strip())
        print("---")
        return

    skillshare_dir.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        f.write(yaml_str)
    print(f"\n✅ Config written to: {config_file}")


def ensure_aspirecode_symlink(project_root: Path, dry_run: bool):
    """Ensure .opencode → .aspirecode symlink for aspirations IDE support."""
    aspire_dir = project_root / ".aspirecode"
    opencode_link = project_root / ".opencode"

    if dry_run:
        if not opencode_link.exists() or opencode_link.is_symlink():
            print("🔗 DRY-RUN — would create: .aspirecode/ and .opencode → .aspirecode symlink")
        return

    aspire_dir.mkdir(parents=True, exist_ok=True)

    if opencode_link.exists():
        if opencode_link.is_symlink():
            current_target = os.readlink(opencode_link)
            if current_target == ".aspirecode":
                return  # Already correct
            opencode_link.unlink()
        elif opencode_link.is_dir():
            print("⚠️  .opencode is a real directory, skipping symlink creation for aspirations")
            return

    opencode_link.symlink_to(".aspirecode")
    print("🔗 Created .opencode → .aspirecode symlink (aspirecode IDE support)")


def run_skillshare_sync(project_root: Path, dry_run: bool):
    """Call skillshare sync -p to distribute skills."""
    # Ensure aspirations symlink before sync
    ensure_aspirecode_symlink(project_root, dry_run)

    cmd = ["skillshare", "sync", "-p"]
    if dry_run:
        cmd.append("--dry-run")

    print(f"\n🔧 Running: {' '.join(cmd)} (cwd={project_root})")

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout:
            print(result.stdout.strip())
        if result.returncode != 0:
            print(f"⚠️  skillshare sync exited with code {result.returncode}")
            if result.stderr:
                print(result.stderr.strip())
        else:
            print("✅ skillshare sync completed")
    except FileNotFoundError:
        print("❌ skillshare CLI is not installed. Skipping sync.")
        print("   Install it from: https://github.com/runkids/skillshare")
        print("   Then run: skillshare sync -p")
    except subprocess.TimeoutExpired:
        print("⚠️  skillshare sync timed out")
    except Exception as e:
        print(f"❌ Failed to run skillshare sync: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    agent_envs = args.agent_envs
    include_raw = args.include_list
    central_src = os.path.expanduser(args.central_src)
    dry_run = args.dry_run
    kimi_path = args.kimi_path

    # Validate project root
    if not project_root.exists():
        print(f"❌ Project root does not exist: {project_root}")
        sys.exit(1)
    if not project_root.is_dir():
        print(f"❌ Not a directory: {project_root}")
        sys.exit(1)

    # Parse include list
    include_list = [s.strip() for s in include_raw.split(",") if s.strip()]
    if not include_list:
        print("⚠️  Empty include list — no skills will be synced")

    # Resolve agents
    agents = resolve_agents(agent_envs)
    if not agents:
        print("❌ No valid agent environments selected")
        sys.exit(1)

    print(f"🎯 Agents: {', '.join(agents)}")
    print(f"📦 Include: {', '.join(include_list)}")
    print(f"📂 Central source: {central_src}")

    if dry_run:
        print("🔍 DRY-RUN mode — no files will be written")

    # Build new targets
    new_targets = []
    for agent in agents:
        entry = build_target_entry(agent, kimi_path)
        if entry is None:
            continue
        new_targets.append(entry)

    if not new_targets:
        print("❌ No targets could be built")
        sys.exit(1)

    # Load existing config for merging
    existing_config = load_existing_config(project_root)

    # Determine sources (preserve existing if present)
    existing_sources = {}
    if existing_config:
        existing_sources = existing_config.get("sources", {})
        # Also check existing targets
        existing_targets = existing_config.get("targets", [])
    else:
        existing_targets = []

    # Merge include lists
    final_targets = merge_include_lists(existing_targets, new_targets, include_list)

    # Build final config
    config = {
        "sources": {
            "skills": central_src,
        },
        "targets": final_targets,
    }

    # If existing config had other sources keys, merge them
    if existing_sources and isinstance(existing_sources, dict):
        for key, value in existing_sources.items():
            if key != "skills":
                config["sources"][key] = value

    # Preserve any existing top-level keys (like audit, ignore, extras)
    if existing_config:
        for key in ("audit", "ignore", "extras"):
            if key in existing_config:
                config[key] = existing_config[key]

    # Write config
    write_config(project_root, config, dry_run)

    # Run skillshare sync
    run_skillshare_sync(project_root, dry_run)


if __name__ == "__main__":
    main()
