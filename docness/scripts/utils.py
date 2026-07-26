"""Docness shared utilities: path handling, filename generation, URL matching."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


def generate_filename(
    original_name: str,
    title_summary: str = "",
    date_str: str = "",
) -> str:
    stem = Path(original_name).stem
    clean_title = re.sub(r"[^\w\u4e00-\u9fff\-]", "", title_summary)[:40]
    today = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    parts = [today, stem]
    if clean_title:
        parts.append(clean_title)
    return "-".join(parts) + ".md"


def generate_url_filename(url: str) -> str:
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d-%H%M%S")
    micro = now.strftime("%f")
    return f"{ts}-{micro}-url.txt"


def detect_file_type(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    mapping: dict[str, str] = {
        ".md": "markdown",
        ".docx": "word",
        ".doc": "word-legacy",
        ".xlsx": "excel",
        ".pptx": "powerpoint",
        ".ppt": "powerpoint-legacy",
        ".pdf": "pdf",
        ".csv": "csv",
        ".txt": "text",
        ".mp3": "audio",
        ".mp4": "video",
        ".wav": "audio",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
    }
    return mapping.get(ext, "unknown")


def match_url_pattern(url: str, patterns: list[tuple[str, str, str]]) -> dict | None:
    for pattern, source_type, skill in patterns:
        if re.search(pattern, url):
            return {"source_type": source_type, "skill": skill, "pattern": pattern}
    return None


def generate_meeting_filename(
    subject: str,
    attendees: list[str],
    date: str,
    suffix: str = "纪要",
) -> tuple[str, str]:
    date_part = date.replace("-", "")[2:8]
    attendee_part = "".join(attendees[:2])
    clean_subject = re.sub(r"[^\w\u4e00-\u9fff\-]", "", subject)[:20]
    filename = f"{date_part}-{attendee_part}-{clean_subject}-{suffix}.md"
    directory = f"{date_part}{clean_subject}"
    return filename, directory


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_markdown_url(url: str) -> bool:
    return url.rstrip("/").endswith(".md")
