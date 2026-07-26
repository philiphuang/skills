#!/usr/bin/env python3
"""preprocess.py — GH12 预处理：mermaid 类型校验 + SVG 引用转换。

在 strip_metadata 之前或之后调用均可（本脚本不碰 front matter）。
分两个独立步骤：

1. validate_mermaid(content) → (content, warnings)
   扫描 ```mermaid 围栏代码块，校验图类型是否在 supported 清单中。
   支持的 → 保持原样（lark-doc 自动渲染白板）
   不支持 → 降级为 <code> 块 + 加告警注释

2. convert_svg_refs(content, base_dir) → (content, svg_mapping)
   扫描 ![alt](./path.svg) 和 <img src="...svg"> 引用
   替换为 <whiteboard type="blank"></whiteboard><!--SVG:ordinal-->
   返回映射表 [{ordinal, svg_path, alt}]

用法：
  python3 preprocess.py --file <MD>                              # 两步都跑
  python3 preprocess.py --file <MD> --skip-svg                   # 只校验 mermaid
  python3 preprocess.py --file <MD> --skip-mermaid               # 只转换 SVG
  python3 preprocess.py --file <MD> --mapping-out mapping.json   # 输出 SVG 映射表
  cat file.md | python3 preprocess.py -
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SUPPORTED_TYPES_PATH = SCRIPT_DIR.parent / "references" / "mermaid-supported-types.json"

with open(SUPPORTED_TYPES_PATH, encoding="utf-8") as f:
    _MERMAID_CONFIG = json.load(f)

_SUPPORTED_TYPES = set(_MERMAID_CONFIG["supported"])
_TYPE_ALIASES = _MERMAID_CONFIG["aliases"]
_FALLBACK_MSG = _MERMAID_CONFIG["fallback"]["message_template"]

_FENCE_RE = re.compile(r"^(`{3,}|~{3,})\s*(.*)$")
_SVG_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+\.svg(?:\?[^)]*)?)\)")
_SVG_HTML_RE = re.compile(r'<img\s[^>]*src="([^"]+\.svg(?:\?[^"]*)?)"[^>]*>')


def _resolve_mermaid_type(content_line: str) -> str | None:
    """从 mermaid 代码块正文首行提取图类型。"""
    # 跳过空行
    cleaned = content_line.strip()
    if not cleaned:
        return None
    # 取第一个词（线条声明如 flowchart LR, graph TD, sequenceDiagram 等）
    first_word = cleaned.split(None, 1)[0].strip()
    if not first_word:
        return None
    # 排除非类型关键词（线条连接符号、注释等）
    if first_word in ("-->", "->>", "->>", "==", "--", "%%", "#"):
        return None
    return _TYPE_ALIASES.get(first_word, first_word)


def validate_mermaid(content: str) -> tuple[str, list[str]]:
    """校验 mermaid 代码块类型，不支持的降级为 <code> 块。

    Args:
        content: markdown 全文。

    Returns:
        (处理后的内容, 告警列表)。
    """
    lines = content.splitlines(keepends=True)
    warnings: list[str] = []
    in_code_block = False
    code_fence = ""
    mermaid_type: str | None = None
    block_start = -1

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        fence_match = _FENCE_RE.match(stripped)

        if not in_code_block:
            if fence_match:
                fence = fence_match.group(1)
                info = fence_match.group(2)
                if info.startswith("mermaid"):
                    in_code_block = True
                    code_fence = fence
                    block_start = i
                    mermaid_type = None  # 暂不处理，等第一行正文
                # 非 mermaid 代码块，跳过
            i += 1
        else:
            if fence_match and fence_match.group(1).startswith(code_fence[0]):
                # 代码块结束
                in_code_block = False
                if mermaid_type is not None and mermaid_type not in _SUPPORTED_TYPES:
                    warnings.append(
                        _FALLBACK_MSG.format(type=mermaid_type)
                    )
                    _degrade_mermaid_block(lines, block_start, i, mermaid_type)
                mermaid_type = None
                i += 1
            else:
                # 代码块正文行
                if mermaid_type is None:
                    mermaid_type = _resolve_mermaid_type(line)
                i += 1

    return "".join(lines), warnings


def _degrade_mermaid_block(lines: list, start: int, end: int, mermaid_type: str = "unknown"):
    """把不支持的 mermaid 代码块降级为 <code> 包裹的代码块。

    在 lines 上原地修改。
    """
    # 替换开头的 ```mermaid → ```code
    first = lines[start]
    new_first = first.replace("```mermaid", "```code", 1)
    new_first = new_first.replace("~~~mermaid", "~~~code", 1)
    lines[start] = new_first
    # 在前一行插入降级告警注释
    comment = f"<!--mermaid:unsupported:{mermaid_type}-->\n"
    lines.insert(start, comment)


def _parse_svg_path(raw: str, base_dir: Path) -> str:
    """解析 SVG 路径，支持相对路径和绝对路径。"""
    # 去掉 query string
    path_str = raw.split("?")[0]
    path = Path(path_str)
    if path.is_absolute():
        return str(path.resolve())
    return str((base_dir / path).resolve())


def convert_svg_refs(content: str, base_dir: str | Path = ".") -> tuple[str, list[dict]]:
    """扫描 markdown 中的 SVG 引用，替换为 whiteboard 占位符。

    Args:
        content: markdown 全文。
        base_dir: markdown 文件所在目录，用于解析相对路径。

    Returns:
        (处理后的内容, SVG 映射表)。
    """
    base = Path(base_dir).resolve()
    svg_mapping: list[dict] = []
    ordinal = [0]  # 用 list 让闭包能修改

    def _replace_img(match: re.Match) -> str:
        alt = match.group(1)
        raw_path = match.group(2)
        abs_path = _parse_svg_path(raw_path, base)
        idx = ordinal[0]
        ordinal[0] += 1
        svg_mapping.append({"ordinal": idx, "svg_path": abs_path, "alt": alt})
        return f'<whiteboard type="blank"></whiteboard><!--SVG:{idx}-->'

    def _replace_html_img(match: re.Match) -> str:
        raw_path = match.group(1)
        abs_path = _parse_svg_path(raw_path, base)
        idx = ordinal[0]
        ordinal[0] += 1
        svg_mapping.append({"ordinal": idx, "svg_path": abs_path, "alt": ""})
        return f'<whiteboard type="blank"></whiteboard><!--SVG:{idx}-->'

    content = _SVG_IMG_RE.sub(_replace_img, content)
    content = _SVG_HTML_RE.sub(_replace_html_img, content)

    return content, svg_mapping


def preprocess(content: str, base_dir: str | Path = ".", *,
               skip_mermaid: bool = False, skip_svg: bool = False) -> tuple[str, list[str], list[dict]]:
    """两步预处理：mermaid 校验 + SVG 转换。

    Args:
        content: markdown 全文。
        base_dir: markdown 文件所在目录。
        skip_mermaid: 跳过 mermaid 校验步骤。
        skip_svg: 跳过 SVG 转换步骤。

    Returns:
        (处理后的内容, 告警列表, SVG 映射表)。
    """
    warnings: list[str] = []
    svg_mapping: list[dict] = []

    if not skip_mermaid:
        content, mermaid_warnings = validate_mermaid(content)
        warnings.extend(mermaid_warnings)

    if not skip_svg:
        content, svg_mapping = convert_svg_refs(content, base_dir)

    return content, warnings, svg_mapping


def main():
    parser = argparse.ArgumentParser(
        description="GH12 预处理：mermaid 类型校验 + SVG 引用转换"
    )
    parser.add_argument("file", nargs="?", help="markdown 文件路径，或 - 从 stdin 读")
    parser.add_argument("-f", "--file", dest="file_alt", help="markdown 文件路径（位置参数别名）")
    parser.add_argument("--skip-mermaid", action="store_true", help="跳过 mermaid 校验")
    parser.add_argument("--skip-svg", action="store_true", help="跳过 SVG 转换")
    parser.add_argument("--mapping-out", help="SVG 映射表 JSON 输出路径")
    parser.add_argument("--warnings-out", help="告警列表 JSON 输出路径")
    parser.add_argument("-o", "--output", help="处理后内容输出路径（默认 stdout）")
    args = parser.parse_args()

    file_arg = args.file or args.file_alt
    if file_arg is None or file_arg == "-":
        content = sys.stdin.read()
        base_dir = Path.cwd()
    else:
        path = Path(file_arg)
        if not path.exists():
            print(f"错误：文件不存在：{path}", file=sys.stderr)
            sys.exit(1)
        content = path.read_text(encoding="utf-8")
        base_dir = path.parent

    result, warnings, svg_mapping = preprocess(
        content, base_dir,
        skip_mermaid=args.skip_mermaid,
        skip_svg=args.skip_svg,
    )

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
    else:
        sys.stdout.write(result)

    if args.mapping_out:
        Path(args.mapping_out).write_text(
            json.dumps(svg_mapping, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.warnings_out:
        Path(args.warnings_out).write_text(
            json.dumps(warnings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if warnings:
        for w in warnings:
            print(w, file=sys.stderr)


if __name__ == "__main__":
    main()
