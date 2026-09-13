#!/usr/bin/env python3
"""clean_copy.py — 生成推送飞书用的 Clean Copy（工作法 §4.4）。

飞书后端会删除 HTML 注释，留在推送内容里的 `<!--feishu:…-->` 行无意义，
必须移除。但正文内的真实受保护元素必须保留：

删除（无意义、会被后端吞掉的注释行）：
  <!--feishu:whiteboard TOKEN 描述 source=…-->
  <!--feishu:image TOKEN 描述-->

保留（真实元素，飞书渲染依赖）：
  <whiteboard type="blank"></whiteboard>   ← 占位符，触发飞书重建白板
  ![alt](path)                              ← 图片 markdown
  ```mermaid … ```                            ← mermaid 代码块（lark-doc 自动创建 + 渲染白板）

中转标记（预处理阶段使用，飞书后端会删除该注释）：
  <!--SVG:N-->                              ← SVG→白板映射标记，与 <whiteboard type="blank"> 同行
  <!--feishu:comments … --> 块              ← 由 strip_metadata 剥离，本脚本兜底跳过

注意：本脚本只处理"行级 feishu 注释"，不动 front matter / h1 / 元数据 blockquote
（那些由 strip_metadata.py 负责）。完整 Clean Copy = strip_metadata 的输出再过本脚本。

用法：
  python3 clean_copy.py --file <MD>                  # 输出 Clean Copy 到 stdout
  python3 clean_copy.py --file <MD> --section '### 2.1'  # 只清洗某章节
  cat file.md | python3 clean_copy.py - 
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strip_metadata import strip_local_metadata  # noqa: E402
from extract_section import extract_section  # noqa: E402


# 匹配行级 feishu 注释标记：以 <!--feishu: 开头的行（comments 块起始也匹配，
# 但 comments 多行块的后续非注释行不在本正则范围；strip_metadata 已先剥离 comments 块）
_FEISHU_MARKER_RE = re.compile(r"^\s*<!--\s*feishu:")


def clean_copy(content: str) -> str:
    """从已 strip_metadata 的内容生成 Clean Copy：删 feishu 注释行、保留真实元素。

    Args:
        content: markdown 全文。建议先过 strip_local_metadata（本函数也会兜底再过一次）。

    Returns:
        Clean Copy：无 front matter、无 comments 块、无 h1 元数据、无 feishu 注释行，
        但保留 <whiteboard type="blank"> 和图片 markdown。
    """
    # 先剥离本地元数据（兜底；调用方通常已先调用 strip_metadata）
    stripped = strip_local_metadata(content)
    lines = stripped.splitlines(keepends=True)

    result = []
    for line in lines:
        if _FEISHU_MARKER_RE.match(line):
            continue  # 删 feishu 注释行
        result.append(line)

    cleaned = "".join(result)
    # 清理可能产生的连续空行（feishu 标记行删除后留下的），最多保留单个空行分隔
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def clean_section(content: str, title_spec: str, explicit_level: int = None) -> str:
    """生成单个章节的 Clean Copy（用于策略 A/B/C 的章节级推送）。

    流程：strip_metadata → extract_section → 删 feishu 注释行。
    """
    stripped = strip_local_metadata(content)
    section = extract_section(stripped.splitlines(), title_spec, explicit_level)
    if not section:
        return ""
    # 章节已是文本片段，删其中的 feishu 注释行
    lines = section.splitlines(keepends=True)
    result = [line for line in lines if not _FEISHU_MARKER_RE.match(line)]
    cleaned = "".join(result)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="生成推送飞书用的 Clean Copy（删 feishu 注释行、保留白板占位符和图片）"
    )
    parser.add_argument("file", help="markdown 文件路径，或 - 从 stdin 读")
    parser.add_argument("--section", help="只清洗指定章节（标题，如 '### 2.1' 或 '2.1'）")
    parser.add_argument("--level", type=int, choices=[1, 2, 3, 4, 5, 6],
                        help="章节层级（--section 不含 # 前缀时必填）")
    parser.add_argument("-o", "--output", help="输出文件路径（默认 stdout）")
    args = parser.parse_args()

    if args.file == "-":
        content = sys.stdin.read()
    else:
        path = Path(args.file)
        if not path.exists():
            print(f"错误：文件不存在：{path}", file=sys.stderr)
            sys.exit(1)
        content = path.read_text(encoding="utf-8")

    if args.section:
        result = clean_section(content, args.section, args.level)
        if not result:
            print(f"⚠️ 未找到章节：{args.section}", file=sys.stderr)
            sys.exit(1)
    else:
        result = clean_copy(content)

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"✅ 已生成 Clean Copy，写入 {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(result)


if __name__ == "__main__":
    main()
