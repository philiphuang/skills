"""留痕（#110 §5）：sync.log 行范式 + router-log.jsonl 分类决策审计。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def log_sync(path: Path, stage: str, title: str, action: str, result: str) -> None:
    """追加一行：时间 | 阶段 | 会话标题 | 动作 | 结果（imness sync.log 范式）。"""
    ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{ts} | {stage} | {title} | {action} | {result}\n")


def log_decision(path: Path, record: dict) -> None:
    """追加一条分类决策审计（含 LLM reason，#109 §3）。"""
    entry = {"logged_at": datetime.now().astimezone().isoformat(timespec="seconds"), **record}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
