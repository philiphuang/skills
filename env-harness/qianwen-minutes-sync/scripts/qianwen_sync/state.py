"""state.json 会话游标（#110 §3 拉取层 watermark）。"""
from __future__ import annotations

import json
from pathlib import Path

from .api import AUDIO_ENTRY

EMPTY = {"conversations": {}}


def load(path: Path) -> dict:
    if not path.exists():
        return {"conversations": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"conversations": {}}
    if not isinstance(doc, dict) or not isinstance(doc.get("conversations"), dict):
        return {"conversations": {}}
    return doc


def save(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select_increment(state: dict, conversations: list[dict]) -> list[dict]:
    """增量条件（run-spec §3）：entry=audio_qianwen 且（不在游标或 updated_at 变化）。"""
    known = state.get("conversations") or {}
    pending: list[dict] = []
    for conv in conversations:
        if conv.get("entry") != AUDIO_ENTRY:
            continue
        cid = str(conv.get("id") or "")
        if not cid:
            continue
        prev = known.get(cid)
        if prev is None or prev.get("updated_at") != conv.get("updated_at"):
            pending.append(conv)
    return pending


def mark_done(state: dict, conv: dict, action: str) -> dict:
    """写游标：done 后 updated_at 再变只更新游标，不触发重归档语义由文件名即状态兜底。"""
    conversations = state.setdefault("conversations", {})
    conversations[str(conv.get("id"))] = {
        "title": conv.get("title"),
        "updated_at": conv.get("updated_at"),
        "done": True,
        "last_action": action,
    }
    return state


def unmark(state: dict, conversation_id: str) -> dict:
    """回滚游标：fetch 失败后调用，删除 done 标记使下次 list-new 重新吐出该会话。"""
    conversations = state.get("conversations") or {}
    conversations.pop(str(conversation_id), None)
    return state
