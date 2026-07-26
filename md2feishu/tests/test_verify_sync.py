"""test_verify_sync.py — verify_sync 单元测试。

验证：同步前后批注/白板/图片/章节数量对比，工作法 §4.6 校验逻辑。
失败检测：白板/批注减少 → critical（可能误用 overwrite），章节减少 → warning。

运行：
  python3 -m pytest skills/md2feishu/tests/test_verify_sync.py
  或：python3 skills/md2feishu/tests/test_verify_sync.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from verify_sync import (  # noqa: E402
    verify, collect_counts, count_whiteboards, count_images,
    count_headings, count_comments, render_report,
)


# ---------- 计数工具 ----------

def test_count_whiteboards():
    content = '<whiteboard type="blank"></whiteboard>\n<whiteboard token="abc"/>'
    assert count_whiteboards(content) == 2


def test_count_whiteboards_none():
    assert count_whiteboards("纯文本") == 0


def test_count_images_markdown():
    content = "![a](x.png)\n![b](y.png)\n文本"
    assert count_images(content) == 2


def test_count_images_xml():
    content = '<img token="t1"/>\n<img href="https://x/y.png"/>'
    assert count_images(content) == 2


def test_count_images_mixed():
    content = "![a](x.png)\n<img token=\"t1\"/>"
    assert count_images(content) == 2


def test_count_headings():
    content = "# H1\n## H2\n### H3\n文本\n#### H4"
    assert count_headings(content) == 4


def test_count_headings_ignores_non_heading():
    # ###无空格 不是合法标题
    content = "## 合法\n###不合法\n文本"
    assert count_headings(content) == 1


def test_count_comments_explicit_count():
    assert count_comments({"comments_count": 5}) == 5


def test_count_comments_from_list():
    assert count_comments({"comments": ["c1", "c2", "c3"]}) == 3


def test_count_comments_from_items_dict():
    assert count_comments({"comments": {"items": [{"id": 1}, {"id": 2}]}}) == 2


def test_count_comments_zero():
    assert count_comments({}) == 0


# ---------- collect_counts ----------

def test_collect_counts():
    snapshot = {
        "doc": "## 一\n<whiteboard type=\"blank\"></whiteboard>\n![a](x.png)",
        "comments_count": 3,
    }
    counts = collect_counts(snapshot)
    assert counts == {"comments": 3, "whiteboards": 1, "images": 1, "headings": 1}


def test_collect_counts_alt_keys():
    """支持 data.document.content 路径。"""
    snapshot = {
        "data": {"document": {"content": "## 一\n## 二"}},
        "comments": [],
    }
    counts = collect_counts(snapshot)
    assert counts["headings"] == 2
    assert counts["comments"] == 0


# ---------- verify：通过场景 ----------

def test_verify_all_preserved_passes():
    """所有维度 after >= before → passed=True。"""
    before = {"doc": "## 一\n## 二\n<whiteboard/>\n![a](x.png)", "comments_count": 5}
    after = {"doc": "## 一\n## 二\n## 三\n<whiteboard/>\n![a](x.png)", "comments_count": 5}
    result = verify(before, after)
    assert result["passed"] is True
    assert result["failed_dims"] == []


def test_verify_new_section_addition_passes():
    """新增章节（after 章节数 > before）正常通过。"""
    before = {"doc": "## 一", "comments_count": 0}
    after = {"doc": "## 一\n## 二\n## 三", "comments_count": 0}
    result = verify(before, after)
    assert result["passed"] is True


def test_verify_new_comment_passes():
    """新增批注（after > before）正常通过。"""
    before = {"doc": "## 一", "comments_count": 3}
    after = {"doc": "## 一", "comments_count": 5}
    assert verify(before, after)["passed"] is True


# ---------- verify：失败场景（工作法 §0.2 错误 1）----------

def test_verify_whiteboard_lost_fails_critical():
    """白板数量减少 → critical 失败（可能误用 overwrite）。"""
    before = {"doc": "<whiteboard type=\"blank\"></whiteboard>", "comments_count": 0}
    after = {"doc": "纯文本，白板没了", "comments_count": 0}
    result = verify(before, after)
    assert result["passed"] is False
    assert "whiteboards" in result["failed_dims"]
    wb_item = next(it for it in result["items"] if it["dim"] == "whiteboards")
    assert wb_item["severity"] == "critical"


def test_verify_comment_lost_fails_critical():
    """批注数量减少 → critical 失败。"""
    before = {"doc": "## 一", "comments_count": 5}
    after = {"doc": "## 一", "comments_count": 3}
    result = verify(before, after)
    assert result["passed"] is False
    assert "comments" in result["failed_dims"]


def test_verify_heading_lost_fails_warning():
    """章节数减少 → warning 失败（结构被破坏）。"""
    before = {"doc": "## 一\n## 二\n## 三", "comments_count": 0}
    after = {"doc": "## 一", "comments_count": 0}
    result = verify(before, after)
    assert result["passed"] is False
    assert "headings" in result["failed_dims"]
    h_item = next(it for it in result["items"] if it["dim"] == "headings")
    assert h_item["severity"] == "warning"


def test_verify_image_lost_fails_warning():
    """图片减少 → warning 失败。"""
    before = {"doc": "![a](x.png)\n![b](y.png)", "comments_count": 0}
    after = {"doc": "![a](x.png)", "comments_count": 0}
    result = verify(before, after)
    assert "images" in result["failed_dims"]


# ---------- render_report ----------

def test_render_report_passed():
    result = {"items": [
        {"dim": "comments", "before": 5, "after": 5, "passed": True, "severity": "critical"},
        {"dim": "whiteboards", "before": 1, "after": 1, "passed": True, "severity": "critical"},
        {"dim": "images", "before": 2, "after": 2, "passed": True, "severity": "warning"},
        {"dim": "headings", "before": 4, "after": 4, "passed": True, "severity": "warning"},
    ], "passed": True, "failed_dims": []}
    report = render_report(result)
    assert "校验通过" in report
    assert "✅" in report


def test_render_report_failed():
    result = {"items": [
        {"dim": "comments", "before": 5, "after": 5, "passed": True, "severity": "critical"},
        {"dim": "whiteboards", "before": 1, "after": 0, "passed": False, "severity": "critical"},
        {"dim": "images", "before": 2, "after": 2, "passed": True, "severity": "warning"},
        {"dim": "headings", "before": 4, "after": 4, "passed": True, "severity": "warning"},
    ], "passed": False, "failed_dims": ["whiteboards"]}
    report = render_report(result)
    assert "校验失败" in report
    assert "白板数" in report
    assert "overwrite" in report  # 提示误用 overwrite


if __name__ == "__main__":
    mod = sys.modules[__name__]
    passed = failed = 0
    for name in sorted(dir(mod)):
        if name.startswith("test_"):
            try:
                getattr(mod, name)()
                print(f"  ✅ {name}")
                passed += 1
            except AssertionError as e:
                print(f"  ❌ {name}: {e}")
                failed += 1
            except Exception as e:
                print(f"  💥 {name}: {type(e).__name__}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
