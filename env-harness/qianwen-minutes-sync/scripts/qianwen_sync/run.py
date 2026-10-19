"""CLI（#111/#202/#206）：v2 getter = list-new / fetch；遗留 v1 = run / finalize。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

from .api import ApiError, QianwenClient, load_cookie
from .archive import STATUS_PENDING, archive_filename, finalize_inbox_file, rescan_inbox, target_dir, write_minute
from .classify import build_ai_prompt, keyword_match
from .getter import cmd_fetch, cmd_list_new
from .report import build_report, cookie_fail_report
from .runlog import log_decision, log_sync
from .state import load as state_load, mark_done, save as state_save, select_increment

DEFAULT_WORKSPACE = "/opt/prjs/2606国际公司MCloud"
DEFAULT_MAP = Path.home() / ".config" / "project-daimon" / "projects-map.yaml"


class ConfigError(RuntimeError):
    pass


def _scratch(workspace: str) -> Path:
    return Path(workspace) / ".scratch" / "qianwen-minutes-sync"


def _load_map(map_path: Path) -> tuple[list[dict], str]:
    if not map_path.exists():
        raise ConfigError(f"projects-map 不存在: {map_path}（先运行 gen_projects_map 生成）")
    doc = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    projects = doc.get("projects") or []
    inbox = (doc.get("defaults") or {}).get("inbox_dir")
    if not inbox:
        raise ConfigError(f"projects-map 缺 defaults.inbox_dir: {map_path}")
    return projects, inbox


def _summary_text(messages: list[dict]) -> str:
    for m in messages:
        if m.get("type") == "summary":
            return (m.get("content") or "").strip()
    return ""


def cmd_run(args: argparse.Namespace) -> int:
    try:
        projects, inbox_dir = _load_map(Path(args.map).expanduser())
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    scratch = _scratch(args.workspace)
    state_path = scratch / "state.json"
    sync_log = scratch / "sync.log"
    router_log = scratch / "router-log.jsonl"
    llm_tasks_path = scratch / "llm-tasks.json"

    try:
        client = QianwenClient(load_cookie(args.cookie, Path(args.cookie_file).expanduser() if args.cookie_file else None))
        client.probe()
    except ApiError as exc:
        print(cookie_fail_report(str(exc)))
        return 2

    state = state_load(state_path)
    pulled_at = datetime.now().astimezone().isoformat(timespec="seconds")
    stats = {"pulled": 0, "archived": 0, "inboxed": 0, "skipped": 0, "rescanned": 0,
             "cookie_ok": True, "inbox_titles": [], "backlog": 0, "llm_tasks": [],
             "llm_tasks_path": str(llm_tasks_path), "errors": [], "dry_run": bool(args.dry_run)}

    if not args.dry_run:
        for dest in rescan_inbox(inbox_dir, projects):
            stats["rescanned"] += 1
            log_sync(sync_log, "重扫待分拣", dest.name, "归档", str(dest))
            log_decision(router_log, {"stage": "rescan", "title": dest.name, "action": "archived",
                                      "file": str(dest), "by": "keyword"})

    conversations = client.audio_conversations()
    fresh = select_increment(state, conversations)
    llm_tasks: list[dict] = []

    for conv in fresh:
        stats["pulled"] += 1
        title = conv.get("title") or "无标题"
        decision = keyword_match(title, projects)
        name = archive_filename(conv)
        exists = (target_dir(decision, inbox_dir) / name).exists()
        messages: list[dict] = []
        if not args.dry_run and not exists:
            try:
                messages = client.messages(str(conv.get("id")))
            except ApiError as exc:
                stats["errors"].append(f"{title}: messages 拉取失败 {exc}")
                continue

        archive_dir = (decision.entry or {}).get("archive_dir")
        if exists:
            stats["skipped"] += 1
            action = "跳过(已存在)"
        elif args.dry_run:
            if archive_dir:
                stats["archived"] += 1
                action = "归档(dry-run)"
            else:
                stats["inboxed"] += 1
                stats["inbox_titles"].append(title)
                if decision.entry is None:
                    llm_tasks.append({
                        "conversation_id": conv.get("id"),
                        "title": title,
                        "prompt": build_ai_prompt(title, _summary_text(messages), projects),
                    })
                action = "待分拣(dry-run)"
        elif archive_dir:
            dest = write_minute(conv, messages, decision, pulled_at, inbox_dir)
            stats["archived"] += 1
            action = f"归档 {dest}"
        else:
            dest = write_minute(conv, messages, decision, pulled_at, inbox_dir)
            stats["inboxed"] += 1
            stats["inbox_titles"].append(title)
            if decision.entry is None:
                llm_tasks.append({
                    "conversation_id": conv.get("id"),
                    "title": title,
                    "prompt": build_ai_prompt(title, _summary_text(messages), projects),
                })
            action = f"待分拣 {dest}"

        if not args.dry_run:
            log_sync(sync_log, "拉取", title, action.split(" ")[0], action)
            log_decision(router_log, {"stage": "pull", "conversation_id": conv.get("id"),
                                      "title": title, "project": (decision.entry or {}).get("id"),
                                      "matched_keyword": decision.matched_keyword,
                                      "confidence": decision.confidence, "action": action.split(" ")[0]})
            state = mark_done(state, conv, action.split(" ")[0])

    inbox_path = Path(inbox_dir)
    stats["backlog"] = len(list(inbox_path.glob("*.md"))) if inbox_path.is_dir() else 0
    stats["llm_tasks"] = llm_tasks

    if not args.dry_run:
        state_save(state_path, state)
        if llm_tasks:
            llm_tasks_path.write_text(json.dumps(llm_tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        elif llm_tasks_path.exists():
            llm_tasks_path.unlink()

    print(build_report(stats))
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    try:
        projects, inbox_dir = _load_map(Path(args.map).expanduser())
        answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    except (ConfigError, json.JSONDecodeError, OSError) as exc:
        print(f"输入错误: {exc}", file=sys.stderr)
        return 2

    scratch = _scratch(args.workspace)
    inbox_path = Path(inbox_dir)
    archived, pending = 0, 0
    for item in answers:
        cid = str(item.get("conversation_id") or "")
        matches = list(inbox_path.glob(f"*-{cid[:12]}.md")) if cid else []
        if not matches:
            print(f"未找到待分拣文件: {cid}", file=sys.stderr)
            continue
        dest, decision = finalize_inbox_file(matches[0], item.get("answer") or "", projects)
        if decision.entry is not None:
            archived += 1
            log_sync(scratch / "sync.log", "LLM判定", matches[0].name, "归档", str(dest))
        else:
            pending += 1
            log_sync(scratch / "sync.log", "LLM判定", matches[0].name, "仍待分拣", "UNCERTAIN")
        log_decision(scratch / "router-log.jsonl", {
            "stage": "finalize", "conversation_id": cid, "title": matches[0].name,
            "project": (decision.entry or {}).get("id"), "confidence": decision.confidence,
            "action": "archived" if decision.entry else "pending",
            "reason": item.get("answer", "")[:200]})

    print(f"LLM 判定完成：归档 {archived}，仍待分拣 {pending}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qianwen_sync",
        description="千问纪要同步工具集（v2 getter + v1 遗留管线）")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE, help=f"运行现场（默认 {DEFAULT_WORKSPACE}）")
    parser.add_argument("--map", default=str(DEFAULT_MAP), help=f"projects-map 路径（默认 {DEFAULT_MAP}；仅 v1 命令使用）")
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list-new", help="增量列出新增录音会话（JSONL，输出即推游标）")
    p_list.add_argument("--state", default=None, help="游标 state.json 路径（默认 v1 现场 state.json）")
    p_list.add_argument("--reset", action="store_true", help="忽略游标，吐全量录音会话")
    p_list.add_argument("--cookie", help="原始 Cookie 头（默认环境变量 QIANWEN_COOKIE 或快照文件）")
    p_list.add_argument("--cookie-file", help="Cookie 快照文件（默认 ~/.config/project-daimon/qianwen-cookie.txt）")
    p_list.set_defaults(func=cmd_list_new)

    p_fetch = sub.add_parser("fetch", help="导出指定会话的官方原文 txt（浏览器通道，agent 中立 getter）")
    p_fetch.add_argument("conversation", help="会话 ID 或 qianwen.com/chat URL")
    p_fetch.add_argument("--out", help="输出 txt 路径（默认当前目录 qianwen-transcript-<ID12>.txt）")
    p_fetch.add_argument("--timeout", type=int, default=90, help="单会话浏览器执行超时秒数（默认 90）")
    p_fetch.add_argument("--cookie", help="原始 Cookie 头（playwright 通道需要；默认环境变量 QIANWEN_COOKIE 或快照文件）")
    p_fetch.add_argument("--cookie-file", help="Cookie 快照文件（默认 ~/.config/project-daimon/qianwen-cookie.txt）")
    p_fetch.add_argument("--state", default=None, help="游标 state.json 路径（默认 v1 现场 state.json）")
    p_fetch.set_defaults(func=cmd_fetch)

    p_run = sub.add_parser("run", help="【遗留 v1】拉取→分类→归档管线（落 归档/纪要/ 体系）")
    p_run.add_argument("--cookie", help="原始 Cookie 头（默认环境变量 QIANWEN_COOKIE 或快照文件）")
    p_run.add_argument("--cookie-file", help=f"Cookie 快照文件（默认 ~/.config/project-daimon/qianwen-cookie.txt）")
    p_run.add_argument("--dry-run", action="store_true", help="只打印报告，不写任何文件/游标")
    p_run.set_defaults(func=cmd_run)

    p_fin = sub.add_parser("finalize", help="【遗留 v1】把 automation agent 的 LLM 判定落到待分拣文件")
    p_fin.add_argument("--answers", required=True, help="JSON 数组：[{conversation_id, answer}]")
    p_fin.set_defaults(func=cmd_finalize)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
