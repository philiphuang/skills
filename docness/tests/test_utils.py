"""Tests for utils.py"""

from pathlib import Path

from scripts.utils import (
    detect_file_type,
    generate_filename,
    generate_url_filename,
    is_markdown_url,
    match_url_pattern,
)


def test_generate_filename():
    name = generate_filename("foo.docx", "会议纪要摘要", "2026-07-19")
    assert name.startswith("2026-07-19")
    assert "foo" in name
    assert "会议纪要摘要" in name
    assert name.endswith(".md")


def test_generate_filename_no_title():
    name = generate_filename("foo.docx")
    assert "foo" in name
    assert name.endswith(".md")


def test_generate_url_filename():
    name = generate_url_filename("https://test.com/doc")
    assert "url.txt" in name
    assert len(name) > 20


def test_detect_file_type():
    assert detect_file_type("test.docx") == "word"
    assert detect_file_type("test.pdf") == "pdf"
    assert detect_file_type("test.xlsx") == "excel"
    assert detect_file_type("test.pptx") == "powerpoint"
    assert detect_file_type("test.md") == "markdown"
    assert detect_file_type("test.csv") == "csv"
    assert detect_file_type("test.txt") == "text"
    assert detect_file_type("test.mp3") == "audio"
    assert detect_file_type("test.mp4") == "video"
    assert detect_file_type("test.png") == "image"
    assert detect_file_type("test.unknown") == "unknown"


def test_is_markdown_url():
    assert is_markdown_url("https://example.com/doc.md") is True
    assert is_markdown_url("https://example.com/doc.md/") is True
    assert is_markdown_url("https://example.com/doc.pdf") is False


def test_match_url_pattern():
    patterns = [
        (r"docs\.qq\.com/doc/", "tencent-doc", "tencent-docs"),
        (r"feishu\.cn/", "feishu", "lark-doc"),
    ]
    result = match_url_pattern("https://docs.qq.com/doc/abc", patterns)
    assert result is not None
    assert result["source_type"] == "tencent-doc"

    result = match_url_pattern("https://unknown.com/doc", patterns)
    assert result is None
