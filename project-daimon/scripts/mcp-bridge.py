#!/usr/bin/env python3
"""mcp-bridge: 把声明式 MCP 源渲染到各 agent 的异构配置格式。

源:  .skillshare/mcp-bridge/servers.yaml (默认，可通过 --source 指定)
目标 agent:
  - zcode       → ~/.claude.json 的 mcpServers (JSON, 复用 Claude Code 体系)
  - kimicode    → <project>/.mcp.json (项目级)
  - kimidesktop → Kimi Desktop 沙箱的 plugin manifest + installed.json + wrapper

子命令:
  list                  列出源里的 server 及其 targets
  diff <target>         显示源 vs agent 现状的差异 (只读)
  sync [--target T]     渲染源到指定/全部 agent (写)
  collect [--target T]  从 agent 现有配置反向收集到源

安全: 写 JSON 前自动备份 (.bak.<ts>); ZCode 的 ~/.claude.json 只 merge mcpServers 段。

依据: docs/agent-onboarding-plan.md
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML: pip install pyyaml")

DEFAULT_SOURCE = ".skillshare/mcp-bridge/servers.yaml"

# 各 agent 的配置路径
ZCODE_MCP = Path.home() / ".claude.json"
KIMI_DESKTOP_SANDBOX = (
    Path.home() / "Library/Application Support/kimi-desktop"
    / "daimon-share/daimon/runtime/kimi-code/home"
)


# ── 源读写 ────────────────────────────────────────────────────────────────
def load_source(source_path: str) -> dict:
    src = Path(source_path)
    if not src.exists():
        sys.exit(f"源不存在: {src}（先建 servers.yaml）")
    return yaml.safe_load(src.read_text()) or {}


def save_source(data: dict, source_path: str) -> None:
    src = Path(source_path)
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def resolve_env(val):
    """env:VAR 形式的值从环境变量读取；未设置时打印警告到 stderr。"""
    if isinstance(val, str) and val.startswith("env:"):
        var_name = val[4:]
        value = os.environ.get(var_name)
        if value is None:
            print(
                f"⚠️ env:{var_name} not set. Please export {var_name}=your_value first.",
                file=sys.stderr,
            )
            return ""
        return value
    return val


def to_agent_config(srv: dict) -> dict:
    """把源里的 server 定义转成 agent 通用的 mcpServers 条目（zcode/kimicode 共用）。"""
    out = {}
    if srv["transport"] == "http":
        out["type"] = "http"
        out["url"] = srv["url"]
        if "headers" in srv:
            out["headers"] = {k: resolve_env(v) for k, v in srv["headers"].items()}
    else:  # stdio
        out["type"] = "stdio"
        out["command"] = srv["command"]
        if "args" in srv:
            out["args"] = srv["args"]
        if "env" in srv:
            out["env"] = {k: resolve_env(v) for k, v in srv["env"].items()}
    return out


# ── 备份 ──────────────────────────────────────────────────────────────────
def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    bak = path.with_name(f"{path.name}.bak.{int(time.time())}")
    shutil.copy2(path, bak)
    return bak


# ── ZCode 渲染 (~/.claude.json) ───────────────────────────────────────────
def zcode_read() -> dict:
    if not ZCODE_MCP.exists():
        return {}
    return json.loads(ZCODE_MCP.read_text()).get("mcpServers", {})


def zcode_sync(servers: dict, dry_run: bool = False) -> list[str]:
    """merge 写入 ~/.claude.json 的 mcpServers。只动 mcpServers 段，保留其他字段。

    用 mcpBridgeManaged 数组持久化"哪些 server 由 mcp-bridge 管理"，从而支持删除：
    源里删掉的 server 会被从 ~/.claude.json 移除（仅限 mcp-bridge 管理的，不碰用户手加的）。
    """
    target_servers = {
        n: to_agent_config(s)
        for n, s in servers.items()
        if "zcode" in s.get("targets", [])
    }
    data = json.loads(ZCODE_MCP.read_text()) if ZCODE_MCP.exists() else {}
    existing = data.get("mcpServers", {})
    prev_managed = set(data.get("mcpBridgeManaged", []))
    now_managed = set(target_servers)
    # 非管理的（既不在 prev_managed 也不在 now_managed）原样保留
    keep_unmanaged = {
        k: v
        for k, v in existing.items()
        if k not in prev_managed and k not in now_managed
    }
    merged = {**keep_unmanaged, **target_servers}
    data["mcpServers"] = merged
    data["mcpBridgeManaged"] = sorted(now_managed)  # 记录管理名单，供下次删除判断
    removed = prev_managed - now_managed
    msg = f"[zcode] 已写入 {len(target_servers)} 个 server → {ZCODE_MCP}"
    if removed:
        msg += f"；移除 {sorted(removed)}"
    if dry_run:
        return [
            f"[zcode dry-run] 会写入 {sorted(target_servers)}"
            + (f"；移除 {sorted(removed)}" if removed else "")
        ]
    bak = backup(ZCODE_MCP)
    ZCODE_MCP.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return [msg + f"（备份 {bak.name if bak else 'N/A'}）"]


# ── Kimi Code 渲染 (项目 .mcp.json) ───────────────────────────────────────
def kimicode_sync(servers: dict, project: Path, dry_run: bool = False) -> list[str]:
    """渲染到指定项目的 .mcp.json。"""
    target_servers = {
        n: to_agent_config(s)
        for n, s in servers.items()
        if "kimicode" in s.get("targets", [])
    }
    out = {"mcpServers": target_servers}
    dest = project / ".mcp.json"
    if dry_run:
        return [f"[kimicode dry-run] 会写入 {dest}: {sorted(target_servers)}"]
    bak = backup(dest) if dest.exists() else None
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return [
        f"[kimicode] 已写入 {len(target_servers)} 个 server → {dest}"
        f"（备份 {bak.name if bak else '新建'}）"
    ]


# ── Kimi Desktop 渲染 (plugin manifest + wrapper + installed.json) ────────
def kimidesktop_sync(servers: dict, dry_run: bool = False) -> list[str]:
    """生成 plugin 目录 + kimi.plugin.json + wrapper(stdio) + 注册 installed.json。

    约束 (实测, 见 plan 4.3):
      - stdio command 限 PATH 命令或 ./ 相对路径 → 生成 bin/wrapper.sh
      - 改后需重启 Kimi Desktop (无热重载)
    """
    base = KIMI_DESKTOP_SANDBOX / "plugins"
    managed = base / "managed"
    installed_json = base / "installed.json"
    target_servers = {
        n: s
        for n, s in servers.items()
        if "kimidesktop" in s.get("targets", [])
    }
    logs = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # 读现有 installed.json
    if installed_json.exists():
        inst = json.loads(installed_json.read_text())
    else:
        inst = {"version": 1, "plugins": []}
    inst_ids = {p["id"]: p for p in inst["plugins"]}
    # 识别 mcp-bridge 管理的插件（originalSource == "mcp-bridge"），用于支持删除清理
    bridge_managed_prev = {
        pid
        for pid, p in inst_ids.items()
        if p.get("originalSource") == "mcp-bridge"
    }

    for name, srv in target_servers.items():
        pdir = managed / name
        pj = pdir / "kimi.plugin.json"
        manifest = {
            "$schema": "https://kimi.com/schemas/kimi.plugin.schema.json",
            "name": name,
            "version": "0.1.0",
            "description": f"mcp-bridge managed: {name}",
            "skills": "./skills/",
            "mcpServers": {},
        }
        if srv["transport"] == "http":
            manifest["mcpServers"][name] = {"url": srv["url"]}
            if "bearerTokenEnvVar" in srv:
                manifest["mcpServers"][name]["bearerTokenEnvVar"] = srv[
                    "bearerTokenEnvVar"
                ]
        else:  # stdio: 生成 wrapper
            (pdir / "bin").mkdir(parents=True, exist_ok=True)
            wrapper = pdir / "bin" / "wrapper.sh"
            cmd = " ".join([srv["command"], *srv.get("args", [])])
            wrapper.write_text(
                "#!/bin/sh\n# 由 mcp-bridge 生成；kimi-code 限 command 为 PATH/相对路径，故经 wrapper 转发\n"
                f'exec {cmd} "$@"\n'
            )
            wrapper.chmod(0o755)
            manifest["mcpServers"][name] = {
                "command": "sh",
                "args": ["./bin/wrapper.sh"],
                "cwd": "./",
            }
        if dry_run:
            logs.append(
                f"[kimidesktop dry-run] 会建插件 {name} ({srv['transport']})"
            )
            continue
        pdir.mkdir(parents=True, exist_ok=True)
        pj.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        # 注册 installed.json
        inst_ids[name] = {
            "id": name,
            "root": str(pdir),
            "source": "local-path",
            "enabled": True,
            "installedAt": now,
            "updatedAt": now,
            "originalSource": "mcp-bridge",
        }
        logs.append(
            f"[kimidesktop] 已建插件 {name} ({srv['transport']}) → {pdir}"
        )

    if not dry_run and target_servers:
        # 清理：源里已删除的 mcp-bridge 管理插件 → 从 installed.json 移除 + 删插件目录
        now_managed = set(target_servers)
        removed = bridge_managed_prev - now_managed
        for rid in removed:
            inst_ids.pop(rid, None)
            rdir = managed / rid
            if rdir.exists():
                shutil.rmtree(rdir)
        if removed:
            logs.append(f"[kimidesktop] 移除已删插件: {sorted(removed)}")
        inst["plugins"] = list(inst_ids.values())
        backup(installed_json)
        installed_json.write_text(
            json.dumps(inst, indent=2, ensure_ascii=False)
        )
        logs.append(
            f"[kimidesktop] 已注册 {len(target_servers)} 插件 → {installed_json}"
        )
        logs.append("[kimidesktop] ⚠️ 需重启 Kimi Desktop 才生效（无热重载）")
    return logs


# ── 子命令 ────────────────────────────────────────────────────────────────
def cmd_list(args):
    data = load_source(args.source)
    servers = data.get("servers", {})
    print(f"源: {args.source}\n共 {len(servers)} 个 server:\n")
    for n, s in servers.items():
        t = s.get("transport", "?")
        targets = ",".join(s.get("targets", []))
        detail = s.get("url") or s.get("command", "")
        print(f"  {n:20} [{t:5}] → {targets:30} {detail[:50]}")


def cmd_diff(args):
    data = load_source(args.source)
    servers = data.get("servers", {})
    if args.target == "zcode":
        existing = set(zcode_read())
    elif args.target == "kimidesktop":
        existing = set()  # 简化: 不深读
    else:
        existing = set()
    wanted = {
        n for n, s in servers.items() if args.target in s.get("targets", [])
    }
    print(f"=== diff: {args.target} ===")
    print(f"  源里要的: {sorted(wanted)}")
    print(f"  agent 现有: {sorted(existing)}")
    print(f"  待新增: {sorted(wanted - existing)}")
    print(f"  待移除(mcp-bridge 管理范围): {sorted((existing & wanted) - wanted)}")


def cmd_sync(args):
    data = load_source(args.source)
    servers = data.get("servers", {})
    logs = []
    if args.target in (None, "zcode"):
        logs += zcode_sync(servers, dry_run=args.dry_run)
    if args.target in (None, "kimicode"):
        proj = Path(args.project).resolve()
        logs += kimicode_sync(servers, proj, dry_run=args.dry_run)
    if args.target in (None, "kimidesktop"):
        logs += kimidesktop_sync(servers, dry_run=args.dry_run)
    for l in logs:
        print(l)


def cmd_collect(args):
    """从 agent 现有配置反向收集到源（保守：只 collect，不删源里已有）。"""
    data = load_source(args.source)
    servers = data.get("servers", {})
    if args.target == "zcode":
        existing = zcode_read()
        for name, cfg in existing.items():
            if name in servers:
                continue  # 源里已有，不覆盖
            transport = (
                "http" if cfg.get("type") == "http" or "url" in cfg else "stdio"
            )
            entry = {"transport": transport, "targets": ["zcode"]}
            if transport == "http":
                entry["url"] = cfg["url"]
            else:
                entry["command"] = cfg.get("command", "")
                if "args" in cfg:
                    entry["args"] = cfg["args"]
            servers[name] = entry
            print(f"  + 收集 {name} [{transport}]")
        data["servers"] = servers
        if not args.dry_run:
            save_source(data, args.source)
            print(f"已保存 → {args.source}")


def main():
    ap = argparse.ArgumentParser(description="mcp-bridge: MCP 多 agent 渲染器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出源里的 server")
    p_list.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help=f"servers.yaml 路径 (默认: {DEFAULT_SOURCE})",
    )

    p_diff = sub.add_parser("diff", help="源 vs agent 差异")
    p_diff.add_argument("target", choices=["zcode", "kimicode", "kimidesktop"])
    p_diff.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help=f"servers.yaml 路径 (默认: {DEFAULT_SOURCE})",
    )

    p_sync = sub.add_parser("sync", help="渲染源到 agent")
    p_sync.add_argument(
        "--target", choices=["zcode", "kimicode", "kimidesktop"]
    )
    p_sync.add_argument(
        "--project", default=".", help="kimicode 的项目目录"
    )
    p_sync.add_argument("--dry-run", "-n", action="store_true")
    p_sync.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help=f"servers.yaml 路径 (默认: {DEFAULT_SOURCE})",
    )

    p_collect = sub.add_parser("collect", help="从 agent 反向收集到源")
    p_collect.add_argument(
        "--target",
        choices=["zcode", "kimicode", "kimidesktop"],
        default="zcode",
    )
    p_collect.add_argument("--dry-run", "-n", action="store_true")
    p_collect.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help=f"servers.yaml 路径 (默认: {DEFAULT_SOURCE})",
    )

    args = ap.parse_args()
    {
        "list": cmd_list,
        "diff": cmd_diff,
        "sync": cmd_sync,
        "collect": cmd_collect,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
