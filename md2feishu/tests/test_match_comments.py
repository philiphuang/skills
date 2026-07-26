"""test_match_comments.py — 批注落点匹配单元测试。

验证：quote 出现在章节文本中的批注被正确命中，未出现的批注被过滤。

运行：
  python3 -m pytest products/md2feishu/tests/test_match_comments.py
  或：python3 products/md2feishu/tests/test_match_comments.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from match_comments import load_comments, match_comments  # noqa: E402


def test_no_hits_when_quote_not_in_section():
    """章节文本中没有 quote 时返回空列表。"""
    comments = [
        {"comment_id": "c1", "quote": "不存在的文字", "content_anchor_id": "blkcn1"},
    ]
    section = "这是完全不同的段落。\n"
    assert match_comments(comments, section) == []


def test_hit_when_quote_in_section():
    """quote 作为子串出现在章节文本中时命中。"""
    comments = [
        {"comment_id": "c1", "quote": "被批注文字", "content_anchor_id": "blkcn1"},
        {"comment_id": "c2", "quote": "另一段", "content_anchor_id": "blkcn2"},
    ]
    section = "这是被批注文字所在的段落。另一段也在。\n"
    hits = match_comments(comments, section)
    assert len(hits) == 2
    assert {h["comment_id"] for h in hits} == {"c1", "c2"}


def test_skips_empty_quote():
    """quote 为空或仅空白时跳过。"""
    comments = [
        {"comment_id": "c1", "quote": "", "content_anchor_id": "blkcn1"},
        {"comment_id": "c2", "quote": "   ", "content_anchor_id": "blkcn2"},
    ]
    section = "任意文本。\n"
    assert match_comments(comments, section) == []


def test_load_comments_from_lark_cli_format():
    """解析 lark-cli drive +list-comments 标准输出格式。"""
    data = {
        "data": {
            "items": [
                {"comment_id": "c1", "quote": "命中文字"},
                {"comment_id": "c2", "quote": "未命中"},
            ]
        }
    }
    # 通过临时文件测试 load_comments
    tmp = Path(__file__).resolve().parent / "_tmp_comments.json"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        comments = load_comments(str(tmp))
        section = "命中文字在这里。"
        hits = match_comments(comments, section)
        assert len(hits) == 1
        assert hits[0]["comment_id"] == "c1"
    finally:
        tmp.unlink()


def test_load_comments_direct_list():
    """兼容 comments 直接是数组的情况。"""
    data = [{"comment_id": "c1", "quote": "命中"}]
    tmp = Path(__file__).resolve().parent / "_tmp_comments_list.json"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        comments = load_comments(str(tmp))
        assert len(comments) == 1
        assert comments[0]["comment_id"] == "c1"
    finally:
        tmp.unlink()


if __name__ == "__main__":
    test_no_hits_when_quote_not_in_section()
    test_hit_when_quote_in_section()
    test_skips_empty_quote()
    test_load_comments_from_lark_cli_format()
    test_load_comments_direct_list()
    print("全部通过")
