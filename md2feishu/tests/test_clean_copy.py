"""test_clean_copy.py — clean_copy 单元测试。

验证：删 feishu 注释行、保留 <whiteboard type="blank"> 占位符和图片 markdown。
用飞书评审工作法的真实测试物料做样本。

运行：
  python3 -m pytest skills/md2feishu/tests/test_clean_copy.py
  或：python3 skills/md2feishu/tests/test_clean_copy.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from clean_copy import clean_copy, clean_section  # noqa: E402

TEST_MATERIAL = Path(__file__).resolve().parent.parent.parent.parent / \
    "src" / "工作法" / "飞书评审" / "tests" / "测试物料.md"


def _read_material():
    return Path(TEST_MATERIAL).read_text(encoding="utf-8")


# ---------- 删 feishu 注释行 ----------

def test_removes_feishu_whiteboard_marker():
    """whiteboard 标记行（含 token 的注释）被删除。"""
    content = (
        "<!--feishu:whiteboard MgKVwsQc8hvxDxbrcNOc7wfqnEe 白板 source=mermaid-->\n"
        "<whiteboard type=\"blank\"></whiteboard>\n"
    )
    result = clean_copy(content)
    assert "feishu:whiteboard" not in result
    assert "<whiteboard type=\"blank\"></whiteboard>" in result


def test_removes_feishu_image_marker():
    """image 标记行（含 token 的注释）被删除，图片 markdown 保留。"""
    content = (
        "<!--feishu:image Y13xb3fluoHoSrxAtH1c6sadnEg 部署架构图-->\n"
        "![部署架构示意图](images/deploy-arch.png)\n"
    )
    result = clean_copy(content)
    assert "feishu:image" not in result
    assert "![部署架构示意图](images/deploy-arch.png)" in result


def test_removes_all_feishu_markers():
    """所有 <!--feishu:...--> 行都被删除。"""
    content = (
        "正文A\n"
        "<!--feishu:whiteboard TOKEN1 白板-->\n"
        "<whiteboard type=\"blank\"></whiteboard>\n"
        "正文B\n"
        "<!--feishu:image TOKEN2 图-->\n"
        "![alt](x.png)\n"
    )
    result = clean_copy(content)
    assert "feishu:" not in result
    assert "正文A" in result
    assert "正文B" in result
    assert "<whiteboard type=\"blank\"></whiteboard>" in result
    assert "![alt](x.png)" in result


# ---------- 保留真实元素 ----------

def test_preserves_whiteboard_placeholder():
    """<whiteboard type="blank"></whiteboard> 占位符保留（触发飞书重建）。"""
    content = "<whiteboard type=\"blank\"></whiteboard>\n"
    assert "<whiteboard type=\"blank\"></whiteboard>" in clean_copy(content)


def test_preserves_image_markdown():
    """图片 markdown（![alt](url)）保留。"""
    content = "![架构图](images/arch.png)\n"
    assert "![架构图](images/arch.png)" in clean_copy(content)


def test_preserves_mermaid_block():
    """mermaid 代码块保留（B 策略白板重建依赖）。"""
    content = (
        "```mermaid\n"
        "graph TD\n"
        "    A --> B\n"
        "```\n"
    )
    result = clean_copy(content)
    assert "```mermaid" in result
    assert "graph TD" in result


# ---------- 剥离本地元数据（兜底） ----------

def test_strips_front_matter():
    """front matter 被剥离（不应进飞书）。"""
    content = (
        "---\n"
        "feishu-doc: ABC123\n"
        "sync:\n"
        "  last_commit: abc\n"
        "---\n\n"
        "## 章节\n正文\n"
    )
    result = clean_copy(content)
    assert "feishu-doc" not in result
    assert "last_commit" not in result
    assert "## 章节" in result


def test_strips_comments_block():
    """<!--feishu:comments ... --> 多行块被剥离。"""
    content = (
        "正文\n\n"
        "<!--feishu:comments\n"
        "cmt_001 | 意见 | ou_x | 2026-06-04 | open\n"
        "fetched: 2026-06-04T08:00:00+08:00\n"
        "-->\n"
    )
    result = clean_copy(content)
    assert "feishu:comments" not in result
    assert "cmt_001" not in result
    assert "正文" in result


def test_strips_h1_and_metadata():
    """首行 h1 + 元数据 blockquote 被剥离。"""
    content = (
        "# 文档标题\n\n"
        "> 变更编号：001\n> 创建日期：2026-06-01\n\n"
        "## 第一章\n正文\n"
    )
    result = clean_copy(content)
    assert "# 文档标题" not in result
    assert "变更编号" not in result
    assert "## 第一章" in result


# ---------- 真实测试物料 ----------

def test_material_clean_copy_has_no_feishu_markers():
    """完整测试物料过 clean_copy 后，无任何 feishu: 标记行。"""
    result = clean_copy(_read_material())
    assert "feishu:" not in result


def test_material_clean_copy_preserves_whiteboards_and_images():
    """测试物料含 3 个白板 + 5 张图片，clean_copy 后占位符和图片 markdown 保留。"""
    result = clean_copy(_read_material())
    # 3 个白板占位符（测试物料 line 50, 76, 还有）
    assert result.count("<whiteboard type=\"blank\"></whiteboard>") >= 2
    # 图片 markdown 保留
    assert "![部署架构示意图](images/deploy-arch.png)" in result


# ---------- clean_section（章节级 Clean Copy）----------

def test_clean_section_removes_marker_keeps_placeholder():
    """章节级 Clean Copy：2.1 章节的 whiteboard 标记删除，占位符保留。"""
    result = clean_section(_read_material(), "### 2.1 总体架构")
    assert "feishu:whiteboard" not in result
    assert "<whiteboard type=\"blank\"></whiteboard>" in result
    assert "2.1.1 接入层" in result  # H4 子节保留


def test_clean_section_experiment_e_no_overflow():
    """章节级 Clean Copy 也遵守实验 E：2.2 不越界到 三、"""
    result = clean_section(_read_material(), "### 2.2 部署架构")
    assert "三、用户旅程" not in result
    assert "部署架构示意图" in result


def test_clean_section_not_found():
    """章节不存在返回空。"""
    assert clean_section(_read_material(), "### 不存在") == ""


# ---------- 边界 ----------

def test_empty_input():
    assert clean_copy("") == "\n" or clean_copy("").strip() == ""


def test_no_markers_unchanged():
    """无 feishu 标记、无元数据时，正文原样保留。"""
    content = "## 章节\n\n正文内容。\n"
    result = clean_copy(content)
    assert "## 章节" in result
    assert "正文内容。" in result


def test_collapses_excess_blank_lines():
    """feishu 标记行删除后留的多余空行被压缩。"""
    content = (
        "段落A\n\n\n"
        "<!--feishu:whiteboard TOKEN-->\n\n\n"
        "段落B\n"
    )
    result = clean_copy(content)
    # 不应出现 3+ 连续换行
    assert "\n\n\n" not in result
    assert "段落A" in result
    assert "段落B" in result


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
