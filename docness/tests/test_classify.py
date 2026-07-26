"""Tests for classify.py"""

from scripts.classify import (
    build_classify_prompt,
    parse_classify_response,
)


def test_build_prompt_includes_categories():
    prompt = build_classify_prompt("测试内容", ["会议纪要", "方案设计"])
    assert "会议纪要" in prompt
    assert "方案设计" in prompt
    assert "测试内容" in prompt
    assert "UNCERTAIN" in prompt


def test_build_prompt_truncates_content():
    long_content = "x" * 3000
    prompt = build_classify_prompt(long_content, ["会议纪要"])
    assert len("x" * 3000) > len(prompt)


def test_parse_valid_response():
    result = parse_classify_response('{"category": "会议纪要", "reason": "包含会议记录"}')
    assert result["category"] == "会议纪要"
    assert result["reason"] == "包含会议记录"


def test_parse_uncertain_response():
    result = parse_classify_response('{"category": "UNCERTAIN", "reason": "无法判断"}')
    assert result["category"] == "UNCERTAIN"


def test_parse_invalid_json():
    result = parse_classify_response("不是 JSON")
    assert result["category"] == "UNCERTAIN"
    assert result["reason"] == "parse_error"


def test_parse_markdown_wrapped_json():
    result = parse_classify_response('```json\n{"category": "需求文档", "reason": "需求列表"}\n```')
    assert result["category"] == "需求文档"
