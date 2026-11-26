"""docness 增量游标。

状态文件为 <state-dir>/.docness-cursor.json：

    {
      "version": 1,
      "last_scan_at": "2026-11-10T06:00:00+00:00",
      "last_ingest_at": "2026-11-10T06:05:00+00:00"
    }

两个字段分别记录扫描、消化动作上次成功推进到的时间点，统一使用 UTC / ISO 8601，
与 state.py 的 imported_at、index.py 的 last_updated 写法一致。

游标单独存放，不写进 docness-index.yml：index.py 的 rebuild_index() 会整体重建索引，
写在一起会被覆盖。采用 JSON 格式只为使用标准库，不引入 PyYAML 依赖。

写入使用临时文件加 os.replace 原子替换，避免定时任务中断时留下半截文件。
commit 只允许水位前进，重复执行结果相同。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CURSOR_NAME = ".docness-cursor.json"
EPOCH = "1970-01-01T00:00:00+00:00"
PHASE_KEYS = {"scan": "last_scan_at", "ingest": "last_ingest_at"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value) -> datetime:
    """兼容 None、datetime、ISO 8601 字符串（含 Z 后缀与不带时区的写法）。"""
    if not value:
        return datetime.fromisoformat(EPOCH)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"时间格式无法解析: {value!r}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def state_file(state_dir: str | Path) -> Path:
    return Path(state_dir) / CURSOR_NAME


def load(state_dir: str | Path) -> dict:
    path = state_file(state_dir)
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            # 文件损坏时另存留查，再按初始水位重建；重扫出的文件由索引与 md5 去重
            backup = path.with_name(
                f"{path.name}.corrupt-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
            )
            try:
                path.replace(backup)
            except OSError:
                pass
            print(
                f"游标文件无法解析，已另存为 {backup.name}，按初始水位重建: {exc}",
                file=sys.stderr,
            )
            data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("version", 1)
    for key in PHASE_KEYS.values():
        data.setdefault(key, EPOCH)
    return data


def save(state_dir: str | Path, data: dict) -> None:
    path = state_file(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".cursor-", suffix=".tmp")
    try:
        try:
            handle = os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise
        with handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def watermark(state_dir: str | Path, phase: str) -> datetime:
    if phase not in PHASE_KEYS:
        raise ValueError(f"phase 只能是 {sorted(PHASE_KEYS)}")
    return parse_ts(load(state_dir)[PHASE_KEYS[phase]])


def commit(state_dir: str | Path, phase: str, ts: datetime) -> dict:
    """把水位推进到 ts，只前进不回退，重复执行结果相同。

    目标值由 autoscan 给出：整批成功时取本轮开始时刻 T，下一轮不再扫描这批文件；
    出现失败时取连续成功段最后一项的 mtime 减 1 微秒，使同一秒内写入的失败项
    在下一轮仍能进入清单。已成功的那一项最多被重新扫描一次，由索引与 md5 去重。
    """
    if phase not in PHASE_KEYS:
        raise ValueError(f"phase 只能是 {sorted(PHASE_KEYS)}")
    key = PHASE_KEYS[phase]
    data = load(state_dir)
    old = parse_ts(data[key])
    target = parse_ts(ts)
    if target <= old:
        return {"changed": False, key: iso(old), "reason": "目标水位不高于当前值"}
    data[key] = iso(target)
    save(state_dir, data)
    return {"changed": True, "from": iso(old), key: iso(target)}
