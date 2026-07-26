"""Front matter read/write and index update for Docness state tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from .index import add_entry, load_index


def _indent_yaml(text: str, spaces: int = 2) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" for line in text.split("\n"))


def read_front_matter(filepath: str | Path) -> dict:
    path = Path(filepath)
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return fm.get("docness", {})


def write_front_matter(filepath: str | Path, docness_data: dict) -> None:
    path = Path(filepath)
    content = path.read_text(encoding="utf-8")

    new_fm = f"---\ndocness:\n{_indent_yaml(yaml.dump(docness_data, allow_unicode=True, default_flow_style=False, sort_keys=False).strip())}\n---"

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = f"{new_fm}\n{parts[2].lstrip()}"
        else:
            content = f"{new_fm}\n{content.lstrip()}"
    else:
        content = f"{new_fm}\n\n{content}"

    path.write_text(content, encoding="utf-8")


def record_collect(
    filepath: str | Path,
    source: str,
    source_type: str,
    category: str,
    original_filename: str = "",
) -> None:
    write_front_matter(filepath, {
        "source": source,
        "source_type": source_type,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "knowledge_category": category,
        "original_filename": original_filename,
        "status": "collected",
        "processing": [],
        "published": [],
    })


def record_process(
    filepath: str | Path,
    action: str,
    skill: str,
    outputs: list[str],
) -> None:
    existing = read_front_matter(filepath)
    existing.setdefault("processing", []).append({
        "action": action,
        "skill": skill,
        "outputs": outputs,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    })
    if existing.get("status") in (None, "collected"):
        existing["status"] = "processed"
    write_front_matter(filepath, existing)


def record_publish(
    filepath: str | Path,
    target: str,
    doc_token: str = "",
    url: str = "",
) -> None:
    existing = read_front_matter(filepath)
    existing.setdefault("published", []).append({
        "target": target,
        "doc_token": doc_token,
        "url": url,
        "published_at": datetime.now(timezone.utc).isoformat(),
    })
    existing["status"] = "published"
    write_front_matter(filepath, existing)


def record_log(
    log_dir: str | Path,
    action: str,
    detail: str,
    status: str = "已完成",
) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{today}-docness.md"

    entry = f"""
## 操作
- 时间：{datetime.now(timezone.utc).strftime('%H:%M')}
- {detail}
- 状态：{status}
"""
    with open(log_file, "a") as f:
        f.write(entry)
