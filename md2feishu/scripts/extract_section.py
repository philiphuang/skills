#!/usr/bin/env python3
"""extract_section.py — 从 markdown 提取指定章节（修实验 E 越界 bug）。

飞书评审工作法实验 E 反复踩坑：章节提取终止条件若只匹配同级标题，遇到更
高级标题会越界，导致 Clean Copy 含越界标题，replace 后飞书文档标题重复。

正确规则（工作法 §4.3，CRITICAL）：
  提取终止条件必须是「遇到任意 ≥ 当前层级的标题」，即 heading level ≤ 当前章节 level。

层级对照：
  H2 `##`   level=2，遇 # 或 ## 停
  H3 `###`  level=3，遇 #/##/### 停  ← 实验 E 场景：遇 H2 必须停
  H4 `####` level=4，遇 #~/#### 停
  H5 `#####` level=5，遇任意标题停

用法：
  python3 extract_section.py --file <MD> --title '### 2.2 部署架构'
  python3 extract_section.py --file <MD> --title '2.2' --level 3
  cat file.md | python3 extract_section.py --title '## 六' - 
"""

import argparse
import re
import sys
from pathlib import Path


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def heading_level(line: str, in_code_block: bool = False):
    """返回该行的标题层级（1-6），非标题返回 None。

    匹配 markdown ATX 标题：`#` 开头 + 空格 + 文本。
    不匹配 `##无空格`（非合法标题）。
    若在代码块内（in_code_block=True），一律返回 None，避免误匹配代码注释。
    """
    if in_code_block:
        return None
    stripped = line.strip()
    m = _HEADING_RE.match(stripped)
    if m:
        return len(m.group(1))
    return None


def _is_code_fence(line: str) -> bool:
    """判断是否为代码块围栏（``` 或 ~~~），返回围栏标记或空字符串。"""
    stripped = line.strip()
    if stripped.startswith("```") or stripped.startswith("~~~"):
        return stripped[:3] if stripped[:3] in ("```", "~~~") else ""
    return ""


def _track_code_block(lines: list, start_idx: int) -> list:
    """扫描行列表，返回每行是否在代码块内的布尔列表。

    支持 ``` 和 ~~~ 围栏代码块，不考虑缩进代码块（罕见且易误伤）。
    """
    in_block = False
    fence = ""
    result = []
    for line in lines:
        f = _is_code_fence(line)
        if f and not in_block:
            in_block = True
            fence = f
        elif f == fence and in_block:
            in_block = False
            fence = ""
        result.append(in_block)
    return result


def parse_heading_spec(title_spec: str):
    """从用户输入的 title spec 解析 (level, heading_text)。

    支持两种输入：
      '### 2.2 部署架构'  → level=3, text='2.2 部署架构'（含 # 前缀）
      '2.2 部署架构'      → level=None, text='2.2 部署架构'（无 #，需 --level）

    Returns:
        (level, text) — level 为 None 表示未指定，需调用方提供。
    """
    m = _HEADING_RE.match(title_spec.strip())
    if m:
        return len(m.group(1)), m.group(2).strip()
    return None, title_spec.strip()


def find_heading_line(lines: list, heading_text: str, level: int):
    """定位标题所在行号。

    匹配条件：行的标题层级 == level，且 heading_text 是该标题文本的子串
    （大小写敏感，允许只输入部分标题文本如 '2.2'）。

    Returns:
        行号（0-based），未找到返回 -1。
    """
    in_code_block = _track_code_block(lines, 0)
    for i, line in enumerate(lines):
        h_level = heading_level(line, in_code_block[i])
        if h_level == level:
            m = _HEADING_RE.match(line.strip())
            if m and heading_text in m.group(2).strip():
                return i
    return -1


def extract_section(lines: list, title_spec: str, explicit_level: int = None) -> str:
    """提取指定章节内容，遇任意 ≥ 当前层级标题停止（实验 E 修正）。

    Args:
        lines: markdown 全文的行列表。
        title_spec: 章节标题，可含 # 前缀（'### 2.2 …'）或纯文本（'2.2 …'）。
        explicit_level: 显式层级（title_spec 不含 # 时必填）。

    Returns:
        章节内容（从标题行到下一个 ≥ 当前层级标题前，含标题行）。
        未找到标题返回空字符串。

    Raises:
        ValueError: 无法确定层级（title_spec 无 # 且 explicit_level 为空）。
    """
    parsed_level, heading_text = parse_heading_spec(title_spec)
    level = explicit_level or parsed_level
    if level is None:
        raise ValueError(
            f"无法确定章节层级：title_spec={title_spec!r} 不含 # 前缀，"
            f"且未提供 --level。请用 '### {heading_text}' 或加 --level。"
        )

    start = find_heading_line(lines, heading_text, level)
    if start < 0:
        return ""

    # 预计算每行是否在代码块内
    in_code_block = _track_code_block(lines, start)

    # 从 start+1 起扫描，遇任意 level ≤ 当前层级（即 ≥ 当前）的标题停止
    for i in range(start + 1, len(lines)):
        h_level = heading_level(lines[i], in_code_block[i])
        if h_level is not None and h_level <= level:  # ≥ 当前层级 → 停止
            return "\n".join(lines[start:i])

    # 扫到文件末尾都没遇到终止标题 → 章节到末尾
    return "\n".join(lines[start:])


def extract_section_from_file(file_path: str, title_spec: str, explicit_level: int = None) -> str:
    """从文件读全文并提取章节。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")
    content = path.read_text(encoding="utf-8")
    return extract_section(content.splitlines(), title_spec, explicit_level)


def main():
    parser = argparse.ArgumentParser(
        description="提取 markdown 章节（遇任意 ≥ 当前层级标题停止，修实验 E 越界 bug）"
    )
    parser.add_argument("--file", help="markdown 文件路径（与 - 二选一）")
    parser.add_argument("-f", dest="file_alt", help="markdown 文件路径（--file 的短别名）")
    parser.add_argument("stdin_file", nargs="?", default=None,
                        help="文件路径（位置参数，或 - 表示 stdin）")
    parser.add_argument("--title", required=True,
                        help="章节标题，可含 # 前缀（'### 2.2 …'）或纯文本")
    parser.add_argument("--level", type=int, choices=[1, 2, 3, 4, 5, 6],
                        help="显式层级（title 不含 # 前缀时必填）")
    args = parser.parse_args()

    # 解析输入源：优先 --file，其次 -f，最后位置参数（支持 -）
    file_arg = args.file or args.file_alt or args.stdin_file

    if file_arg is None:
        print("错误：未指定输入文件（用 --file、-f 或位置参数传入）", file=sys.stderr)
        sys.exit(2)

    if file_arg == "-":
        content = sys.stdin.read()
        lines = content.splitlines()
        try:
            result = extract_section(lines, args.title, args.level)
        except ValueError as e:
            print(f"错误：{e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            result = extract_section_from_file(file_arg, args.title, args.level)
        except (ValueError, FileNotFoundError) as e:
            print(f"错误：{e}", file=sys.stderr)
            sys.exit(1)

    if not result:
        print(f"⚠️ 未找到章节：{args.title}（level={args.level}）", file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(result if result.endswith("\n") else result + "\n")


if __name__ == "__main__":
    main()
