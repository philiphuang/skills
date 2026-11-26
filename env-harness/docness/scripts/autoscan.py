"""docness 自动扫描与增量消化。

从 docness 目录执行，分三步完成一轮增量：

    python3 -m scripts.autoscan pending --phase scan \
        --state-dir "<知识库绝对路径>" --scope "<收件箱绝对路径>" \
        --out /tmp/docness-pending.json

    # 按清单逐项执行 collect 或 ingest，把成功的文件路径逐行写入 /tmp/docness-ok.txt

    python3 -m scripts.autoscan commit \
        --pending /tmp/docness-pending.json --ok /tmp/docness-ok.txt

判定规则：本轮开始时刻记为 T，只处理 mtime 落在 (水位, T] 区间的文件；
扫描过程中新落盘的文件留给下一轮。水位按 mtime 升序只推进到连续成功段的
最后一项，遇到失败即停，失败项及其后的文件下一轮重新进入清单，因此不需要
维护逐文件状态表也能避免遗漏。整批成功时水位直接推进到 T，不重复扫描。

本脚本只负责判定、产出清单和推进水位，格式转换仍由 collect SOP 调用
pandoc / MinerU 等工具完成，增量消化由 llm-wiki ingest 完成。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import cursor

DEFAULT_EXTS = {
    # 扫描阶段处理收件箱里的原始素材
    "scan": {
        ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".wps",
        ".pdf", ".csv", ".txt", ".md", ".url",
        ".mp3", ".mp4", ".wav", ".m4a",
    },
    # 消化阶段处理已入库的文本产物
    "ingest": {".md", ".txt", ".csv"},
}

SKIP_DIRS = {
    ".trash", ".logs", ".wiki-tmp", "工作台",
    ".git", "node_modules", "__pycache__",
}
SKIP_NAMES = {".docness-cursor.json", "docness-index.yml", ".wiki-cache.json"}
INGEST_SKIP_NAMES = SKIP_NAMES | {"index.md", "log.md"}


def norm_path(value: str | Path) -> str:
    """统一成可比较的绝对路径，兼容 Windows 的大小写与分隔符差异。"""
    return os.path.normcase(str(Path(value).resolve()))


def iter_files(scope: str | Path, exts: set[str] | None, skip_names: set[str]):
    root = Path(scope).resolve()
    if not root.is_dir():
        raise SystemExit(f"扫描目录不存在: {root}")
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts[:-1]
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel_parts):
            continue
        if path.name.startswith(".") or path.name in skip_names:
            continue
        if exts and path.suffix.lower() not in exts:
            continue
        yield path


def pending_items(
    scope: str | Path,
    wm: datetime,
    T: datetime,
    exts: set[str] | None,
    skip_names: set[str],
) -> list[dict]:
    items = []
    for path in iter_files(scope, exts, skip_names):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError as exc:
            # 扫描期间文件被移走或不可读，跳过本轮，下一轮仍会进入清单
            print(f"跳过无法读取的文件 {path}: {exc}", file=sys.stderr)
            continue
        if wm < mtime <= T:
            items.append({"path": str(path.resolve()), "mtime": cursor.iso(mtime)})
    items.sort(key=lambda item: (item["mtime"], item["path"]))
    return items


def cmd_pending(args: argparse.Namespace) -> int:
    T = cursor.utcnow()
    wm = cursor.watermark(args.state_dir, args.phase)
    exts = None if args.all_files else DEFAULT_EXTS[args.phase]
    skip_names = INGEST_SKIP_NAMES if args.phase == "ingest" else SKIP_NAMES
    items = pending_items(args.scope, wm, T, exts, skip_names)

    payload = {
        "phase": args.phase,
        "state_dir": str(Path(args.state_dir).resolve()),
        "scope": str(Path(args.scope).resolve()),
        "watermark_before": cursor.iso(wm),
        "T": cursor.iso(T),
        "count": len(items),
        "items": items,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

    if args.quiet:
        print(json.dumps({"count": len(items), "out": args.out or ""}, ensure_ascii=False))
    else:
        print(text)
    return 0


def read_pending(path: str | Path) -> dict:
    file = Path(path)
    if not file.is_file():
        raise SystemExit(f"增量清单不存在: {file}")
    try:
        payload = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise SystemExit(f"增量清单无法解析: {file} ({exc})") from exc
    if not isinstance(payload, dict):
        raise SystemExit("增量清单格式错误，请用 pending 子命令重新生成")
    missing = [key for key in ("phase", "state_dir", "T", "items") if key not in payload]
    if missing:
        raise SystemExit(f"增量清单缺少字段 {', '.join(missing)}，请重新生成")
    if payload["phase"] not in cursor.PHASE_KEYS:
        raise SystemExit(f"增量清单 phase 无效: {payload['phase']}")
    if not isinstance(payload["items"], list):
        raise SystemExit("增量清单 items 格式错误，请重新生成")
    for item in payload["items"]:
        if not isinstance(item, dict) or not item.get("path") or not item.get("mtime"):
            raise SystemExit("增量清单含不完整的条目，请重新生成")
    return payload


def cmd_commit(args: argparse.Namespace) -> int:
    payload = read_pending(args.pending)
    items = payload["items"]

    if args.all_ok:
        ok = {norm_path(item["path"]) for item in items}
    else:
        if not args.ok:
            raise SystemExit("需要指定 --ok <成功清单文件>，或改用 --all-ok")
        ok_file = Path(args.ok)
        if not ok_file.is_file():
            raise SystemExit(f"成功清单不存在: {ok_file}")
        ok = set()
        for line in ok_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                ok.add(norm_path(line))

    last_ok = None
    blocked = None
    accepted = 0
    for item in items:
        if norm_path(item["path"]) in ok:
            last_ok = item
            accepted += 1
        else:
            blocked = item["path"]
            break

    if last_ok is None:
        print(json.dumps({
            "changed": False,
            "reason": "没有成功项，水位保持不变，失败项下一轮重新进入清单",
            "blocked_by": blocked,
        }, ensure_ascii=False, indent=2))
        return 0

    if blocked is None:
        target = cursor.parse_ts(payload["T"])
        mode = "all_success_to_T"
    else:
        target = cursor.parse_ts(last_ok["mtime"]) - timedelta(microseconds=1)
        mode = "partial_to_last_ok"

    result = cursor.commit(payload["state_dir"], payload["phase"], target)
    result["mode"] = mode
    result["accepted"] = accepted
    result["committed_through"] = last_ok["path"]
    result["blocked_by"] = blocked
    result["remaining"] = len(items) - accepted
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="docness 增量扫描与消化（mtime 双水位）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pending", help="输出增量清单，不推进水位")
    p.add_argument("--phase", choices=sorted(cursor.PHASE_KEYS), required=True)
    p.add_argument("--state-dir", required=True,
                   help="知识库绝对路径，.docness-cursor.json 存放于此")
    p.add_argument("--scope", required=True, help="要扫描的目录绝对路径")
    p.add_argument("--out", help="清单 JSON 落盘路径，默认只打印")
    p.add_argument("--all-files", action="store_true", help="不限制扩展名")
    p.add_argument("--quiet", action="store_true", help="只打印数量与清单路径")
    p.set_defaults(func=cmd_pending)

    c = sub.add_parser("commit", help="按连续成功段推进水位")
    c.add_argument("--pending", required=True, help="pending 阶段产出的增量清单")
    c.add_argument("--ok", help="成功文件路径清单，一行一个")
    c.add_argument("--all-ok", action="store_true", help="清单内全部成功")
    c.set_defaults(func=cmd_commit)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
