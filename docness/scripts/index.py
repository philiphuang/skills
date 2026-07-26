"""docness-index.yml maintenance."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml


DEFAULT_INDEX_PATH = "知识库/docness-index.yml"


def load_index(index_path: str | Path = DEFAULT_INDEX_PATH) -> dict:
    path = Path(index_path)
    if not path.exists():
        return {"version": "1.0", "last_updated": "", "entries": []}
    with open(path) as f:
        return yaml.safe_load(f) or {"version": "1.0", "last_updated": "", "entries": []}


def save_index(index: dict, index_path: str | Path = DEFAULT_INDEX_PATH) -> None:
    index["last_updated"] = datetime.now(timezone.utc).isoformat()
    Path(index_path).parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w") as f:
        yaml.dump(index, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def add_entry(
    entry: dict,
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> None:
    index = load_index(index_path)
    index.setdefault("entries", []).append(entry)
    save_index(index, index_path)


def find_by_category(
    category: str, index_path: str | Path = DEFAULT_INDEX_PATH
) -> list[dict]:
    index = load_index(index_path)
    return [e for e in index.get("entries", []) if e.get("category") == category]


def find_by_source(
    source: str, index_path: str | Path = DEFAULT_INDEX_PATH
) -> list[dict]:
    index = load_index(index_path)
    return [e for e in index.get("entries", []) if source in (e.get("source") or "")]


def rebuild_index(
    kb_dir: str | Path = "知识库",
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> dict:
    kb = Path(kb_dir)
    entries = []
    for md_file in kb.rglob("*.md"):
        entries.append({
            "path": str(md_file),
            "category": md_file.parent.name,
            "status": "collected",
        })
    index = {
        "version": "1.0",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }
    save_index(index, index_path)
    return index
