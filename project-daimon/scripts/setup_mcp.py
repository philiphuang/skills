#!/usr/bin/env python3
"""
Setup MCP servers for project-daimon using mcp-bridge.

Generates .skillshare/mcp-bridge/servers.yaml with user-selected MCPs,
then calls mcp-bridge.py sync to render to agent configs (zcode, kimicode).

Usage:
    python3 scripts/setup_mcp.py <project-root> [--mcps tavily,anysearch] [--dry-run]
"""

import argparse
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML: pip install pyyaml")


# 所有可用的 MCP 服务器定义
ALL_MCP_SERVERS = {
    "tavily": {
        "transport": "http",
        "url": "https://mcp.tavily.com/mcp/",
        "targets": ["zcode", "kimicode"],
        "headers": {
            "Authorization": "env:TAVILY_API_KEY",
        },
    },
    "anysearch": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "anysearch-mcp"],
        "targets": ["zcode", "kimicode"],
        "env": {
            "ANYSEARCH_API_KEY": "env:ANYSEARCH_API_KEY",
        },
    },
    "exa": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "exa-mcp"],
        "targets": ["zcode", "kimicode"],
        "env": {
            "EXA_API_KEY": "env:EXA_API_KEY",
        },
    },
    "deepwiki": {
        "transport": "http",
        "url": "https://mcp.deepwiki.com/mcp/",
        "targets": ["zcode", "kimicode"],
        "headers": {
            "Authorization": "env:DEEPWIKI_API_KEY",
        },
    },
    "context7": {
        "transport": "http",
        "url": "https://mcp.context7.com/mcp",
        "targets": ["zcode", "kimicode"],
        "headers": {
            "Authorization": "env:CONTEXT7_API_KEY",
        },
    },
    "notebooklm": {
        "transport": "http",
        "url": "https://notebooklm.googleapis.com/v1/mcp",
        "targets": ["zcode", "kimicode"],
        "headers": {
            "Authorization": "env:GOOGLE_API_KEY",
        },
    },
}


def generate_servers_yaml(
    project_path: Path, selected_mcps: list[str], extra_targets: list[str] | None = None
) -> Path:
    """在项目目录下生成 .skillshare/mcp-bridge/servers.yaml。
    
    extra_targets: 额外追加到每个 MCP 的 targets 列表（如 kimidesktop）。"""
    servers = {}
    for name in selected_mcps:
        if name in ALL_MCP_SERVERS:
            srv = dict(ALL_MCP_SERVERS[name])  # shallow copy
            if extra_targets:
                srv["targets"] = srv["targets"] + [t for t in extra_targets if t not in srv["targets"]]
            servers[name] = srv

    yaml_path = project_path / ".skillshare" / "mcp-bridge" / "servers.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    data = {"servers": servers}
    yaml_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    )

    print(f"✅ servers.yaml 已生成 → {yaml_path}")
    return yaml_path


def run_mcp_bridge_sync(
    project_path: Path, source_path: str, dry_run: bool = False
) -> None:
    """调用 mcp-bridge.py sync 渲染到 agent 配置。"""
    script_dir = Path(__file__).resolve().parent
    bridge_script = script_dir / "mcp-bridge.py"

    if not bridge_script.exists():
        sys.exit(f"mcp-bridge.py 未找到: {bridge_script}")

    cmd = [
        sys.executable,
        str(bridge_script),
        "sync",
        "--source",
        source_path,
        "--project",
        str(project_path),
    ]
    if dry_run:
        cmd.append("--dry-run")

    print(f"\n🔧 执行: {' '.join(cmd)}")
    print("-" * 40)
    result = subprocess.run(cmd, cwd=str(project_path))
    if result.returncode != 0:
        sys.exit(f"mcp-bridge sync 失败，退出码: {result.returncode}")
    print("-" * 40)
    print("✅ mcp-bridge sync 完成")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Setup MCP servers for project-daimon using mcp-bridge"
    )
    ap.add_argument(
        "project_root", help="项目根目录路径"
    )
    ap.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="仅预览，不实际写入",
    )
    ap.add_argument(
        "--mcps",
        default="tavily,anysearch",
        help="逗号分隔的 MCP 服务器列表 "
        f"(可选: {', '.join(ALL_MCP_SERVERS)})",
    )
    ap.add_argument(
        "--kimidesktop",
        action="store_true",
        help="同时渲染 MCP 配置到 Kimi Desktop 沙箱",
    )
    args = ap.parse_args()

    project_path = Path(args.project_root).resolve()
    if not project_path.exists():
        sys.exit(f"项目目录不存在: {project_path}")

    selected = [m.strip() for m in args.mcps.split(",") if m.strip()]
    invalid = [m for m in selected if m not in ALL_MCP_SERVERS]
    if invalid:
        sys.exit(
            f"未知 MCP: {invalid}，可用: {list(ALL_MCP_SERVERS)}"
        )

    print(f"🔧 为 project-daimon 配置 MCP: {', '.join(selected)}")

    # 确定额外 targets（如 Kimi Desktop）
    extra_targets = []
    if args.kimidesktop:
        extra_targets.append("kimidesktop")
        print(f"🔧 Kimi Desktop 模式已启用（额外 target: kimidesktop）")

    # Step 1: 生成 servers.yaml
    yaml_path = generate_servers_yaml(project_path, selected, extra_targets)

    # Step 2: 调用 mcp-bridge sync
    source_rel = yaml_path.relative_to(project_path)
    run_mcp_bridge_sync(project_path, str(source_rel), dry_run=args.dry_run)

    print(f"\n🎉 MCP 配置完成！")
    if args.dry_run:
        print("   (dry-run 模式，未实际写入)")
    else:
        print(f"   配置文件已写入项目目录")


if __name__ == "__main__":
    main()
