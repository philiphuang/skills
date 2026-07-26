"""test_extract_section.py — extract_section 单元测试。

重点：实验 E 回归（H3 后遇 H2 不越界）+ H2/H3/H4/H5 边界全覆盖。
用飞书评审工作法的真实测试物料做样本。

运行：
  python3 -m pytest skills/md2feishu/tests/test_extract_section.py
  或：python3 skills/md2feishu/tests/test_extract_section.py
"""

import sys
from pathlib import Path

# 让脚本能直接 import（不依赖 pytest 安装也能跑）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from extract_section import (  # noqa: E402
    extract_section, heading_level, parse_heading_spec,
)

# 测试物料真实路径：tests/ → md2feishu/ → skills/ → 仓库根（回溯 4 个 .parent）
TEST_MATERIAL = Path(__file__).resolve().parent.parent.parent.parent / \
    "src" / "工作法" / "飞书评审" / "tests" / "测试物料.md"


def _load_material():
    """读测试物料全文，返回行列表。"""
    return Path(TEST_MATERIAL).read_text(encoding="utf-8").splitlines()


# ---------- 工具函数测试 ----------

def test_heading_level_h2():
    assert heading_level("## 二、系统架构") == 2


def test_heading_level_h3():
    assert heading_level("### 2.1 总体架构") == 3


def test_heading_level_h5():
    assert heading_level("##### 3.1.2.1 手机号验证") == 5


def test_heading_level_non_heading():
    assert heading_level("普通段落") is None
    assert heading_level("###无空格非标题") is None  # 无空格，非合法 ATX
    assert heading_level("- 列表项") is None


def test_parse_heading_spec_with_hash():
    level, text = parse_heading_spec("### 2.1 总体架构")
    assert level == 3
    assert text == "2.1 总体架构"


def test_parse_heading_spec_plain_text():
    level, text = parse_heading_spec("2.1 总体架构")
    assert level is None
    assert text == "2.1 总体架构"


# ---------- 实验 E 核心回归测试（H3 → H2 不越界）----------

def test_experiment_e_h3_followed_by_h2_no_overflow():
    """实验 E：提取 H3 '2.2 部署架构'，下一个是 H2 '三、用户旅程'。

    错误做法（sed '/^### …/,/^### /p'）会把 H2 也吞进来，导致 replace 后标题重复。
    正确：遇任意 ≥ 当前层级（H2 level=2 < H3 level=3）的标题停止。
    """
    result = extract_section(_load_material(), "### 2.2 部署架构")
    assert "2.2 部署架构" in result
    assert "三、用户旅程" not in result, "实验 E 回归失败：H2 被越界包含进 H3 章节！"
    assert "部署架构示意图" in result  # 章节正文


def test_experiment_e_explicit_level_h3():
    """纯文本标题 + 显式 --level 也能正确终止。"""
    result = extract_section(_load_material(), "2.2 部署架构", explicit_level=3)
    assert "三、用户旅程" not in result


# ---------- H2 边界 ----------

def test_h2_stops_at_next_h2():
    """H2 章节提取，遇下一个 H2 停止。"""
    result = extract_section(_load_material(), "## 一、产品概述")
    assert "一、产品概述" in result
    assert "1.1 项目背景" in result  # 含子节
    assert "二、系统架构" not in result, "H2 越界：包含了下一个 H2"


def test_h2_stops_at_h1_if_present():
    """H2 遇 H1 也应停止（H1 level=1 < H2 level=2）。
    测试物料无 H1 正文标题（h1 是文档标题被 strip），构造用例。"""
    lines = [
        "## 目标章节",
        "内容",
        "# 另一个 H1",
        "其他",
    ]
    result = extract_section(lines, "## 目标章节")
    assert "另一个 H1" not in result
    assert "内容" in result


# ---------- H3 边界 ----------

def test_h3_includes_h4_children():
    """H3 章节含其 H4 子节（H4 level=4 > H3 level=3，不触发停止）。"""
    result = extract_section(_load_material(), "### 2.1 总体架构")
    assert "2.1 总体架构" in result
    assert "2.1.1 接入层" in result  # H4 子节应被包含
    assert "2.1.3 数据层" in result
    assert "2.2 部署架构" not in result  # 下一个 H3 停止


def test_h3_stops_at_next_h3():
    """H3 遇同级 H3 停止。"""
    result = extract_section(_load_material(), "### 1.1 项目背景")
    assert "1.1 项目背景" in result
    assert "1.2 目标用户" not in result  # 同级 H3 停止


# ---------- H4 边界 ----------

def test_h4_includes_h5_children():
    """H4 章节含其 H5 子节（H5 level=5 > H4 level=4）。"""
    result = extract_section(_load_material(), "#### 3.1.2 步骤二：注册账号")
    assert "3.1.2" in result
    assert "3.1.2.1 手机号验证" in result  # H5 子节包含
    assert "3.1.2.2 密码规则" in result
    assert "3.1.3 步骤三" not in result  # 下一个 H4 停止


def test_h4_stops_at_h3_parent_sibling():
    """H4 遇 H3（父级兄弟）应停止（H3 level=3 < H4 level=4）。
    3.1.3 之后是 ### 3.2。"""
    result = extract_section(_load_material(), "#### 3.1.3 步骤三：创建首个项目")
    assert "3.1.3" in result
    assert "3.2 核心业务流程" not in result  # H3 停止


# ---------- H5 边界 ----------

def test_h5_stops_at_next_h5():
    """H5 遇同级 H5 停止。"""
    result = extract_section(_load_material(), "##### 3.1.2.1 手机号验证")
    assert "3.1.2.1" in result
    assert "TC-08" in result  # 章节正文标记
    assert "3.1.2.2 密码规则" not in result  # 同级 H5 停止


def test_h5_stops_at_h4_parent_sibling():
    """H5 遇 H4（父级）也应停止。"""
    # 3.1.2.2 之后是 #### 3.1.3
    result = extract_section(_load_material(), "##### 3.1.2.2 密码规则")
    assert "3.1.2.2" in result
    assert "3.1.3" not in result  # H4 停止


# ---------- 边界与异常 ----------

def test_section_to_end_of_file():
    """章节后无更高/同级标题，提取到文件末尾。
    最后一节 '5.2 安全要求' 后是 comments 块，应到文件末尾。"""
    result = extract_section(_load_material(), "### 5.2 安全要求")
    assert "5.2 安全要求" in result
    assert "安全要求附图" in result


def test_section_not_found():
    """未找到标题返回空字符串。"""
    result = extract_section(_load_material(), "### 不存在的章节")
    assert result == ""


def test_partial_title_match():
    """标题文本只需是子串匹配（'2.2' 匹配 '2.2 部署架构'）。"""
    result = extract_section(_load_material(), "### 2.2")
    assert "部署架构" in result


def test_level_required_for_plain_text():
    """纯文本标题（无 #）且未指定 level 应报错。"""
    try:
        extract_section(_load_material(), "总体架构")
        assert False, "应抛 ValueError"
    except ValueError as e:
        assert "层级" in str(e) or "level" in str(e)


def test_code_block_heading_not_matched():
    """代码块内的 # 行不应被识别为标题（边界防护）。"""
    md = """\
## 真实章节

```python
# 这是代码注释，不是标题
print("hello")
```

## 下一章节
"""
    result = extract_section(md.splitlines(), "## 真实章节")
    assert "真实章节" in result
    assert "下一章节" not in result  # 代码块内的 # 不应触发终止
    assert "代码注释" in result       # 代码块内容应保留


def test_code_block_heading_termination_still_works():
    """代码块后正常标题仍能终止章节。"""
    md = """\
## 真实章节

内容在此。

```bash
# 安装依赖
npm install
```

## 下一章节

后续内容。
"""
    result = extract_section(md.splitlines(), "## 真实章节")
    assert "真实章节" in result
    assert "内容在此" in result
    assert "安装依赖" in result       # 代码块内容保留
    assert "下一章节" not in result   # 代码块后的 H2 正确终止


def test_heading_level_with_code_block():
    """heading_level 在代码块内返回 None。"""
    from extract_section import _track_code_block
    lines = [
        "## 真实标题",
        "```",
        "# 代码注释",
        "```",
        "### 子标题",
    ]
    in_block = _track_code_block(lines, 0)
    assert heading_level(lines[0], in_block[0]) == 2
    assert heading_level(lines[1], in_block[1]) is None  # 围栏行
    assert heading_level(lines[2], in_block[2]) is None  # 代码块内
    assert heading_level(lines[3], in_block[3]) is None  # 围栏行
    assert heading_level(lines[4], in_block[4]) == 3


def test_no_overflow_multiple_h3_in_a_row():
    """连续多个 H3 章节，提取中间一个不应吞掉后续。"""
    # 1.1 → 1.2 → 1.3 连续 H3
    result = extract_section(_load_material(), "### 1.2 目标用户")
    assert "1.2 目标用户" in result
    assert "1.3 核心价值主张" not in result  # 下一个 H3 不被吞
    assert "二、系统架构" not in result


if __name__ == "__main__":
    # 不装 pytest 也能跑：手动调用所有 test_ 函数
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
