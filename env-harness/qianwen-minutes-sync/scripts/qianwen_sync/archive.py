"""归档落地（#108 archive-spec）：命名、front-matter、正文渲染、写入与待分拣重扫。"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml

from .classify import Decision, keyword_match

ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')
MAX_TITLE_LEN = 40
STATUS_ARCHIVED = "archived"
STATUS_PENDING = "pending"


def sanitize_title(title: str) -> str:
    """去非法文件名字符、空白折叠单空格、截 40 字（archive-spec §2）。"""
    cleaned = ILLEGAL_CHARS.sub(" ", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return (cleaned[:MAX_TITLE_LEN] or "无标题").strip()


def to_datetime(ts) -> datetime:
    """兼容 epoch 秒/毫秒与 ISO 字符串（create_time 实际格式未实测，#111 验证点）。"""
    if isinstance(ts, datetime):
        return ts.astimezone()
    if isinstance(ts, (int, float)):
        return _from_epoch(ts)
    text = str(ts or "").strip()
    if text.isdigit():
        return _from_epoch(int(text))
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return datetime.now().astimezone()


def _from_epoch(n: float) -> datetime:
    return datetime.fromtimestamp(n / 1000 if n > 1e12 else n).astimezone()


def archive_filename(conv: dict) -> str:
    """YYYY-MM-DD-标题40字-ID前12.md（archive-spec §2，日期=录音时间 create_time）。"""
    day = to_datetime(conv.get("create_time")).strftime("%Y-%m-%d")
    cid = str(conv.get("id") or "")[:12]
    return f"{day}-{sanitize_title(conv.get('title'))}-{cid}.md"


def source_url(conv: dict) -> str:
    return f"https://www.qianwen.com/chat/{conv.get('id')}?entry=audio_qianwen"


def _minutes_meta(messages: list[dict]) -> dict:
    for m in messages:
        if m.get("type") == "minutes_meta":
            meta = m.get("meta")
            return meta if isinstance(meta, dict) else {}
    return {}


def _format_duration(seconds) -> str:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "未知"
    return f"{int(seconds) // 60} 分 {int(seconds) % 60} 秒"


def build_front_matter(conv: dict, messages: list[dict], decision: Decision, pulled_at: str,
                       status: str = STATUS_ARCHIVED) -> dict:
    """docness 8 字段 + qianwen 顶层键（archive-spec §3）。
    纪要正文接口被验签墙挡住（2026-09 改版实测），minutes_id/note_id/duration 落
    front-matter 作 v1 存根与后续升级锚点；正文走 docness.source 直达链接。"""
    entry = decision.entry or {}
    meta = _minutes_meta(messages)
    qianwen = {
        "conversation_id": conv.get("id"),
        "recorded_at": to_datetime(conv.get("create_time")).isoformat(timespec="seconds"),
        # 转写说话人为「发言人N」编号非真名（web 实测，#107 验证点），无法自动填
        "speakers": [],
        "classification": {
            "project": entry.get("id"),
            "matched_keyword": decision.matched_keyword,
            "confidence": decision.confidence,
            "status": status,
        },
    }
    for fm_key, meta_key in (("minutes_id", "minutes_id"), ("note_id", "note_id"),
                             ("duration_seconds", "duration"), ("minutes_status", "minutes_status")):
        if meta.get(meta_key) is not None:
            qianwen[fm_key] = meta[meta_key]
    return {
        "docness": {
            "source": source_url(conv),
            "source_type": "qianwen-audio",
            "imported_at": pulled_at,
            "knowledge_category": "会议纪要",
            "original_filename": archive_filename(conv),
            "status": "collected",
            "processing": [],
            "published": [],
        },
        "qianwen": qianwen,
    }


def render_markdown(conv: dict, messages: list[dict], decision: Decision,
                    pulled_at: str, status: str = STATUS_ARCHIVED) -> str:
    """front-matter + 正文（摘要 / 说话人分段 / 正文存根 / 其他消息计数）。"""
    fm = build_front_matter(conv, messages, decision, pulled_at, status)
    summaries = [m for m in messages if m.get("type") == "summary"]
    transcriptions = [m for m in messages if m.get("type") == "transcription"]
    others = [m for m in messages if m.get("type") not in ("summary", "transcription", "minutes_meta")]
    meta = _minutes_meta(messages)

    parts = ["---", yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip(), "---", ""]
    parts.append(f"# {conv.get('title') or '无标题'}")
    parts += ["", "## 摘要", ""]
    parts += [((m.get("content") or "").strip() or "（空）") for m in summaries] or ["（无）"]
    parts += ["", "## 说话人分段", ""]
    parts += [((m.get("content") or "").strip()) for m in transcriptions if (m.get("content") or "").strip()] or ["（无）"]
    parts += ["", "## 正文", ""]
    if meta:
        parts.append(f"- 纪要标题：{meta.get('minutes_title') or conv.get('title') or '无标题'}")
        parts.append(f"- 录音时长：{_format_duration(meta.get('duration'))}")
        if meta.get("minutes_status"):
            parts.append(f"- 生成状态：{meta['minutes_status']}")
        parts.append("- 完整正文（AI 纪要与逐句转写）在千问 web 端：点击 front-matter `docness.source` 直达链接查看")
    else:
        parts.append("（未取到纪要元数据；点击 front-matter `docness.source` 直达链接查看）")
    parts += ["", "<!-- 其他消息类型计数: " + _type_counts(others) + " -->", ""]
    return "\n".join(parts)


def _type_counts(messages: list[dict]) -> str:
    counts: dict[str, int] = {}
    for m in messages:
        key = f"{m.get('role')}/{m.get('type')}"
        counts[key] = counts.get(key, 0) + 1
    return ", ".join(f"{k}×{v}" for k, v in sorted(counts.items())) or "无"


def target_dir(decision: Decision, inbox_dir: str | Path) -> Path:
    entry = decision.entry or {}
    archive = entry.get("archive_dir")
    return Path(archive) if archive else Path(inbox_dir)


def write_minute(conv: dict, messages: list[dict], decision: Decision,
                 pulled_at: str, inbox_dir: str | Path) -> Path:
    """写入归档/待分拣文件。文件名即状态：目标存在即跳过（archive-spec §2）。"""
    name = archive_filename(conv)
    dest = target_dir(decision, inbox_dir) / name
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    status = STATUS_ARCHIVED if (decision.entry or {}).get("archive_dir") else STATUS_PENDING
    dest.write_text(render_markdown(conv, messages, decision, pulled_at, status), encoding="utf-8")
    return dest


def _split_front_matter(text: str) -> tuple[dict | None, str, str]:
    """返回 (yaml 对象或 None, front-matter 原文, 正文)。文件头无 --- 块则 (None, '', 全文)。"""
    if not text.startswith("---"):
        return None, "", text
    end = text.find("\n---", 3)
    if end < 0:
        return None, "", text
    fm_text = text[4:end]
    body = text[end + 4:]
    try:
        return yaml.safe_load(fm_text) or {}, fm_text, body
    except yaml.YAMLError:
        return None, "", text


def _title_of_markdown(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def rescan_inbox(inbox_dir: str | Path, projects: list[dict]) -> list[Path]:
    """重扫待分拣（#109 §3）：pending 且第一段已能确定性命中的文件自动归档。"""
    inbox = Path(inbox_dir)
    moved: list[Path] = []
    if not inbox.is_dir():
        return moved
    for path in sorted(inbox.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        fm, _fm_text, body = _split_front_matter(text)
        if not fm:
            continue
        classification = (fm.get("qianwen") or {}).get("classification") or {}
        if classification.get("status") != STATUS_PENDING:
            continue
        decision = keyword_match(_title_of_markdown(body), projects)
        if decision.entry is None or not decision.entry.get("archive_dir"):
            continue
        dest = Path(decision.entry["archive_dir"]) / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_apply_decision(text, fm, decision), encoding="utf-8")
        path.unlink()
        moved.append(dest)
    return moved


def _apply_decision(text: str, fm: dict, decision: Decision) -> str:
    """把新判定写回 front-matter（classification 四字段），正文保持原样。"""
    qianwen = fm.setdefault("qianwen", {})
    qianwen["classification"] = {
        "project": decision.entry.get("id"),
        "matched_keyword": decision.matched_keyword,
        "confidence": decision.confidence,
        "status": STATUS_ARCHIVED,
    }
    return "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip() + "\n---\n" + text[text.find("\n---", 3) + 4:].lstrip("\n")


def finalize_inbox_file(path: Path, answer_text: str, projects: list[dict]) -> tuple[Path, Decision]:
    """第二段落地（#109）：用 agent 的 JSON 判定更新待分拣文件，命中则归档。"""
    from .classify import parse_llm_decision

    text = path.read_text(encoding="utf-8")
    fm, _fm_text, _body = _split_front_matter(text)
    if not fm:
        raise ValueError(f"缺少 front-matter: {path}")
    decision = parse_llm_decision(answer_text, projects)
    if decision.entry is None or not decision.entry.get("archive_dir"):
        return path, decision
    dest = Path(decision.entry["archive_dir"]) / path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_apply_decision(text, fm, decision), encoding="utf-8")
    path.unlink()
    return dest, decision
