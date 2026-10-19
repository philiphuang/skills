#!/usr/bin/env python3
"""gen_projects_map.py — 从项目根目录扫描生成通用项目映射表 projects-map.yaml。

用法:
    python3 gen_projects_map.py --dir /opt/prj [--out PATH] [--init-from PATH] [--dry-run]

projects-map 是通用的「项目 → 目录/关键词」映射（project-daimon 命名空间），
qianwen-minutes-sync 等管线是它的消费方。输出默认落在用户命名空间
~/.config/project-daimon/projects-map.yaml（不写进 skill/仓库空间）。
已存在的同名条目按 project_dir 合并：手工维护的 keywords/archive_dir/id 原样保留，
新发现的目录追加，已删目录只报告不删条目。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

DEFAULT_OUT = Path.home() / ".config" / "project-daimon" / "projects-map.yaml"

# 项目识别信号（满足其一即视为项目目录）
WORKSPACE_MARKERS = {"工作台", "收件箱", "发件箱", "知识库", "归档", "工作法", "AGENTS.md", "CLAUDE.md"}
NUMBERED_PREFIX = re.compile(r"^\d{2}")  # 目录名以两位以上数字开头（如 2607科创平台、24 05 卓语平台）

# 归档子目录推导：项目内已有「归档」则归 归档/纪要，否则 纪要/
ARCHIVE_MARKER = "归档"
ARCHIVE_SUBDIR = "纪要"


def is_project_dir(path: Path) -> bool:
    """判断一个一级子目录是否像项目目录（编号前缀或带工作台/收件箱等标记）。"""
    if not path.is_dir() or path.name.startswith("."):
        return False
    if NUMBERED_PREFIX.match(path.name):
        return True
    return any((path / m).exists() for m in WORKSPACE_MARKERS)


def derive_archive_dir(project_dir: Path) -> str:
    """项目内已有「归档」目录 → 归档/纪要；否则 → 纪要/。"""
    archive_root = project_dir / ARCHIVE_MARKER
    base = archive_root if archive_root.is_dir() else project_dir
    return str(base / ARCHIVE_SUBDIR)


def derive_keywords(project_dir: Path) -> list[str]:
    """关键词草拟：目录名 + 有意义的子目录名（去掉工作台类标记），最多 6 个。"""
    keywords = [project_dir.name]
    for child in sorted(project_dir.iterdir()):
        if child.name in WORKSPACE_MARKERS or child.name.startswith(("_", ".")):
            continue
        if child.is_dir() and len(child.name) >= 2 and child.name not in keywords:
            keywords.append(child.name)
    return keywords[:6]


def scan_root(root: Path, exclude: set[str] | None = None) -> list[dict]:
    """扫描 root 的一级子目录，返回发现的 projects 条目草稿。exclude 为目录名集合，永久跳过。"""
    exclude = exclude or set()
    entries = []
    for child in sorted(root.iterdir()):
        if child.name in exclude:
            continue
        if not is_project_dir(child):
            continue
        entries.append({
            "id": child.name,
            "name": child.name,
            "project_dir": str(child),
            "archive_dir": derive_archive_dir(child),
            "keywords": derive_keywords(child),
            "note": "auto: 由 gen_projects_map 扫描生成，关键词为草拟，请人工校订",
        })
    return entries


def merge(existing: list[dict] | None, discovered: list[dict]) -> tuple[list[dict], list[str]]:
    """合并规则：按 project_dir 键，existing 优先（保手工编辑），discovered 仅追加新目录。"""
    report: list[str] = []
    merged: list[dict] = list(existing or [])
    known_dirs = {e.get("project_dir") for e in merged if e.get("project_dir")}
    for entry in discovered:
        if entry["project_dir"] in known_dirs:
            report.append(f"保留手工条目: {entry['name']}")
            continue
        merged.append(entry)
        report.append(f"新增条目: {entry['name']}")
    # 已删目录不自动清理，仅提示
    discovered_dirs = {e["project_dir"] for e in discovered}
    for e in merged:
        d = e.get("project_dir")
        if d and d not in discovered_dirs:
            report.append(f"目录已不存在(保留条目待人工处理): {e.get('name', d)}")
    return merged, report


HEADER = """\
# 通用项目映射表 / projects-map（project-daimon 命名空间，用户空间配置）
# 由 gen_projects_map 生成并合并手工编辑；消费方（如 qianwen-minutes-sync 管线）按 keywords
# 匹配标题，命中归 archive_dir，无命中或 archive_dir 为空 → 待分拣收件箱（defaults.inbox_dir）。
# 注意：重新生成会重写注释，请把需要长期保留的说明写进 note 字段。
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="扫描项目目录生成 projects-map.yaml")
    parser.add_argument("--dir", required=True, help="项目根目录（如 /opt/prjs）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"输出路径（默认 {DEFAULT_OUT}）")
    parser.add_argument("--init-from", help="输出不存在时的种子配置（如仓库内示例模板）")
    parser.add_argument("--dry-run", action="store_true", help="只报告不写文件")
    args = parser.parse_args(argv)

    root = Path(args.dir).expanduser()
    if not root.is_dir():
        print(f"错误: 目录不存在 {root}", file=sys.stderr)
        return 1

    out_path = Path(args.out).expanduser()
    existing: list[dict] | None = None
    exclude: set[str] = set()
    doc: dict | None = None
    source_path = out_path if out_path.exists() else (Path(args.init_from).expanduser() if args.init_from else None)
    if source_path and source_path.exists():
        doc = yaml.safe_load(source_path.read_text()) or {}
        existing = doc.get("projects")
        exclude = set(doc.get("exclude") or [])

    discovered = scan_root(root, exclude)
    merged, report = merge(existing, discovered)

    if not isinstance(doc, dict) or not doc:
        doc = {"version": 1, "defaults": {"inbox_dir": "待配置", "match": "title"}}
    doc["projects"] = merged

    print(f"扫描 {root}: 发现 {len(discovered)} 个项目目录，合并后共 {len(merged)} 条")
    for line in report:
        print(f"  - {line}")
    print(f"输出: {out_path}")

    if args.dry_run:
        return 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(HEADER + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已写入 {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
