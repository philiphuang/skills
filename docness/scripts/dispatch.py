"""Input recognition and intent routing."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Ensure docness root is on sys.path for absolute imports
_docness_root = str(Path(__file__).resolve().parent.parent)
if _docness_root not in sys.path:
    sys.path.insert(0, _docness_root)

from scripts.utils import (
    detect_file_type,
    generate_filename,
    generate_url_filename,
    is_markdown_url,
    match_url_pattern,
)

URL_PATTERNS: list[tuple[str, str, str]] = [
    (r"docs\.qq\.com/sheet/", "tencent-sheet", "tencent-docs.export_file"),
    (r"docs\.qq\.com/doc/", "tencent-doc", "tencent-docs.export_file"),
    (r"docs\.qq\.com/slide/", "tencent-slide", "tencent-docs.export_file"),
    (r"docs\.qq\.com/docx/", "tencent-smartdoc", "tencent-docs.get_content"),
    (r"docs\.qq\.com/", "tencent-docs", "tencent-docs.get_content"),
    (r"feishu\.cn/docx/", "feishu-doc", "lark-doc"),
    (r"feishu\.cn/minutes/", "feishu-minutes", "lark-minutes"),
    (r"feishu\.cn/vc/", "feishu-vc", "lark-vc"),
    (r"larksuite\.com/", "lark", "lark-doc"),
    (r"meeting\.tencent\.com/", "tencent-meeting", "tencent-meeting-mcp"),
]

COLLECT_TRIGGERS = {"收集", "下载", "拉取", "保存", "归档", "整理", "录制"}
PROCESS_TRIGGERS = {"配图", "生成 ppt", "生成PPT", "转 pdf", "转 PDF", "转 word", "转 Word"}
SEND_TRIGGERS = {"推送", "发送", "上传", "发布", "同步"}


def classify_input(raw: str) -> dict:
    raw_stripped = raw.strip()

    is_url = raw_stripped.startswith("http://") or raw_stripped.startswith("https://")
    local_path = Path(raw_stripped).expanduser()
    is_local = local_path.exists()

    if is_url:
        if is_markdown_url(raw_stripped):
            intent = _detect_intent(raw_stripped) or "send"
            return {
                "type": "url",
                "subtype": "markdown",
                "intent": intent,
                "source_type": "markdown-url",
                "url": raw_stripped,
            }

        match = match_url_pattern(raw_stripped, URL_PATTERNS)
        if match:
            intent = _detect_intent(raw_stripped) or "collect"
            return {
                "type": "url",
                "subtype": match["source_type"],
                "intent": intent,
                "source_type": match["source_type"],
                "skill": match["skill"],
                "url": raw_stripped,
            }

        intent = _detect_intent(raw_stripped) or "collect"
        return {
            "type": "url",
            "subtype": "webpage",
            "intent": intent,
            "source_type": "webpage",
            "url": raw_stripped,
        }

    if is_local:
        file_type = detect_file_type(local_path)
        intent = _detect_intent(raw_stripped) or (
            "send" if file_type == "markdown" else "collect"
        )
        return {
            "type": "local",
            "subtype": file_type,
            "intent": intent,
            "source_type": file_type,
            "path": str(local_path),
            "filename": generate_filename(
                local_path.name, "", str(Path(raw_stripped).stat().st_atime)[:10]
            ),
        }

    url_match = re.search(r'https?://[^\s\n\r]+', raw_stripped)
    if url_match:
        url = url_match.group(0).rstrip(".,;:！），)")
        url_pattern_match = match_url_pattern(url, URL_PATTERNS)
        if url_pattern_match:
            intent = _detect_intent(raw_stripped) or "collect"
            return {
                "type": "url",
                "subtype": url_pattern_match["source_type"],
                "intent": intent,
                "source_type": url_pattern_match["source_type"],
                "skill": url_pattern_match["skill"],
                "url": url,
            }

    intent = _detect_intent(raw_stripped)
    return {
        "type": "text",
        "intent": intent or "unknown",
        "text": raw_stripped,
    }


def _detect_intent(text: str) -> str | None:
    lower = text.lower()
    for t in SEND_TRIGGERS:
        if t in lower:
            return "send"
    for t in PROCESS_TRIGGERS:
        if t in lower:
            return "process"
    for t in COLLECT_TRIGGERS:
        if t in lower:
            return "collect"
    return None


def main():
    if len(sys.argv) < 2:
        result = classify_input(sys.stdin.read())
    else:
        result = classify_input(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
