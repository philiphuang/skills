"""test_preprocess.py — preprocess 单元测试。

验证：mermaid 类型校验 + SVG 引用转换 + 不支持降级。

运行：
  python3 -m pytest products/md2feishu/tests/test_preprocess.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from preprocess import validate_mermaid, convert_svg_refs, preprocess  # noqa: E402


# ---------- mermaid 类型校验 ----------

def test_supported_mermaid_unchanged():
    """支持的 mermaid 类型保持原样。"""
    content = (
        "## 流程图\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "    A --> B\n"
        "```\n"
    )
    result, warnings = validate_mermaid(content)
    assert "```mermaid" in result
    assert "flowchart LR" in result
    assert warnings == []


def test_supported_mermaid_all_types():
    """支持的流程图类型保持原样，不支持的降级。"""
    # flowchart 是唯一 lark-doc 支持的类型
    content = "```mermaid\nflowchart LR\nA-->B\n```\n"
    result, warnings = validate_mermaid(content)
    assert "```mermaid" in result
    assert warnings == []

    # sequenceDiagram 等不被支持 → 降级
    for mtype in ["sequenceDiagram", "classDiagram", "pie", "gantt",
                   "stateDiagram-v2", "erDiagram", "gitGraph", "mindmap"]:
        c = f"```mermaid\n{mtype}\nA-->B\n```\n"
        r, w = validate_mermaid(c)
        assert "```code" in r, f"type={mtype} 未降级"
        assert len(w) == 1, f"type={mtype} 缺警告"


def test_graph_alias_unchanged():
    """graph 旧语法（别名）保持原样。"""
    content = (
        "```mermaid\n"
        "graph TD\n"
        "    A --> B\n"
        "```\n"
    )
    result, warnings = validate_mermaid(content)
    assert "```mermaid" in result
    assert "graph TD" in result
    assert warnings == []


def test_unsupported_mermaid_degraded():
    """不支持的 mermaid 类型降级为 code 块并告警。"""
    content = (
        "```mermaid\n"
        "journey\n"
        "    title My day\n"
        "```\n"
    )
    result, warnings = validate_mermaid(content)
    assert "```mermaid" not in result
    assert "```code" in result
    assert len(warnings) == 1
    assert "journey" in warnings[0]


def test_multiple_mermaid_mixed():
    """混合支持/不支持类型，各按规则处理。"""
    content = (
        "## 流程图\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "A-->B\n"
        "```\n\n"
        "## 旅程图\n\n"
        "```mermaid\n"
        "journey\n"
        "title Day\n"
        "```\n"
    )
    result, warnings = validate_mermaid(content)
    assert "```mermaid" in result
    assert "```code" in result
    assert len(warnings) == 1


def test_non_mermaid_code_block_unchanged():
    """非 mermaid 代码块不受影响。"""
    content = (
        "```python\n"
        "print('hello')\n"
        "```\n"
    )
    result, warnings = validate_mermaid(content)
    assert result == content
    assert warnings == []


# ---------- SVG 引用转换 ----------

def test_svg_image_markdown():
    """![alt](./x.svg) 被替换为 whiteboard 占位符。"""
    content = "![架构图](./images/diagram.svg)\n"
    result, mapping = convert_svg_refs(content)
    assert "![架构图](./images/diagram.svg)" not in result
    assert '<whiteboard type="blank"></whiteboard><!--SVG:0-->' in result
    assert len(mapping) == 1
    assert mapping[0]["ordinal"] == 0
    assert mapping[0]["alt"] == "架构图"


def test_svg_html_img():
    """<img src="x.svg"> 被替换为 whiteboard 占位符。"""
    content = '<img src="./images/arch.svg" alt="arch"/>\n'
    result, mapping = convert_svg_refs(content)
    assert '<whiteboard type="blank"></whiteboard><!--SVG:0-->' in result
    assert len(mapping) == 1


def test_svg_multiple_refs():
    """多个 SVG 引用按序映射。"""
    content = (
        "![图1](a.svg)\n"
        "正文\n"
        "![图2](b.svg)\n"
    )
    result, mapping = convert_svg_refs(content)
    assert '<!--SVG:0-->' in result
    assert '<!--SVG:1-->' in result
    assert len(mapping) == 2
    assert mapping[0]["ordinal"] == 0
    assert mapping[1]["ordinal"] == 1


def test_svg_relative_path_resolution():
    """相对路径以 base_dir 为基准解析。"""
    with tempfile.TemporaryDirectory() as tmp:
        svg_dir = Path(tmp) / "images"
        svg_dir.mkdir()
        svg_file = svg_dir / "test.svg"
        svg_file.write_text("<svg></svg>")

        content = "![test](./images/test.svg)\n"
        result, mapping = convert_svg_refs(content, base_dir=tmp)
        assert mapping[0]["svg_path"] == str(svg_file.resolve())


def test_png_image_not_affected():
    """普通图片（PNG/JPEG/GIF）不受影响。"""
    content = (
        "![图1](image.png)\n"
        "![图2](photo.jpg)\n"
        "![图3](anim.gif)\n"
    )
    result, mapping = convert_svg_refs(content)
    assert result == content  # 原样
    assert mapping == []


def test_svg_absolute_path():
    """绝对路径的 SVG 引用。"""
    content = "![abs](/absolute/path/diagram.svg)\n"
    result, mapping = convert_svg_refs(content)
    assert mapping[0]["svg_path"] == "/absolute/path/diagram.svg"


def test_svg_with_query_string():
    """带 query string 的 SVG 路径。"""
    content = "![图标](icon.svg?refresh=1)\n"
    result, mapping = convert_svg_refs(content)
    assert mapping[0]["svg_path"].endswith("icon.svg")
    assert "?refresh=1" not in mapping[0]["svg_path"]


# ---------- 完整两步预处理 ----------

def test_preprocess_full():
    """完整两步：mermaid 校验 + SVG 转换。"""
    content = (
        "---\nfeishu-doc: TOKEN\n---\n\n"
        "## 测试\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "A-->B\n"
        "```\n\n"
        "```mermaid\n"
        "pie\n"
        "title Pie\n"
        "\"A\" : 50\n"
        "```\n\n"
        "![架构](arch.svg)\n"
    )
    result, warnings, mapping = preprocess(content)
    # flowchart 应保留
    assert "```mermaid" in result
    # pie 不被 lark-doc 支持 → 降级
    assert "```code" in result
    # SVG 应被替换
    assert "![架构](arch.svg)" not in result
    assert "<!--SVG:0-->" in result
    assert len(mapping) == 1


def test_preprocess_unsupported_mermaid_with_svg():
    """不支持 mermaid + SVG 混合处理。"""
    content = (
        "```mermaid\n"
        "journey\n"
        "title Day\n"
        "```\n\n"
        "![x](x.svg)\n"
    )
    result, warnings, mapping = preprocess(content)
    assert "```code" in result  # 降级
    assert len(warnings) == 1
    assert "journey" in warnings[0]
    assert len(mapping) == 1


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
