"""Tests for dispatch.py"""

import json
import tempfile
from pathlib import Path

import pytest

from scripts.dispatch import classify_input


def test_markdown_url():
    result = classify_input("https://example.com/doc.md")
    assert result["type"] == "url"
    assert result["subtype"] == "markdown"
    assert result["intent"] == "send"


def test_tencent_doc_url():
    result = classify_input("https://docs.qq.com/doc/abc123")
    assert result["type"] == "url"
    assert result["subtype"] == "tencent-doc"
    assert result["intent"] == "collect"


def test_tencent_sheet_url():
    result = classify_input("https://docs.qq.com/sheet/abc123")
    assert result["type"] == "url"
    assert result["subtype"] == "tencent-sheet"


def test_tencent_smartdoc_url():
    result = classify_input("https://docs.qq.com/docx/abc123")
    assert result["type"] == "url"
    assert result["subtype"] == "tencent-smartdoc"


def test_feishu_url():
    result = classify_input("https://a.feishu.cn/docx/abc123")
    assert result["type"] == "url"
    assert result["subtype"] == "feishu-doc"


def test_feishu_minutes_url():
    result = classify_input("https://a.feishu.cn/minutes/abc123")
    assert result["type"] == "url"
    assert result["subtype"] == "feishu-minutes"


def test_tencent_meeting_url():
    result = classify_input("https://meeting.tencent.com/abc123")
    assert result["type"] == "url"
    assert result["subtype"] == "tencent-meeting"


def test_generic_webpage_url():
    result = classify_input("https://example.com/article")
    assert result["type"] == "url"
    assert result["subtype"] == "webpage"
    assert result["intent"] == "collect"


def test_local_md_file():
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        f.write(b"# test")
        tmp = Path(f.name)

    try:
        result = classify_input(str(tmp))
        assert result["type"] == "local"
        assert result["subtype"] == "markdown"
        assert result["intent"] == "send"
    finally:
        tmp.unlink()


def test_local_docx_file():
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        f.write(b"PK\x03\x04")
        tmp = Path(f.name)

    try:
        result = classify_input(str(tmp))
        assert result["type"] == "local"
        assert result["subtype"] == "word"
        assert result["intent"] == "collect"
    finally:
        tmp.unlink()


def test_local_pdf_file():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4")
        tmp = Path(f.name)

    try:
        result = classify_input(str(tmp))
        assert result["type"] == "local"
        assert result["subtype"] == "pdf"
        assert result["intent"] == "collect"
    finally:
        tmp.unlink()


def test_collect_trigger():
    result = classify_input("收集这个 https://docs.qq.com/doc/abc")
    assert result["intent"] == "collect"


def test_send_trigger():
    result = classify_input("推送到飞书 知识库/foo.md")
    assert result["intent"] == "send"


def test_process_trigger():
    result = classify_input("配图 知识库/foo.md")
    assert result["intent"] == "process"


def test_plain_text_no_trigger():
    result = classify_input("这是一段话，帮我分析一下")
    assert result["type"] == "text"
    assert result["intent"] == "unknown"
