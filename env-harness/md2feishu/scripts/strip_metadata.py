#!/usr/bin/env python3
"""strip_metadata.py — 推送飞书前剥离本地元数据（飞书评审工作法规则 2）。

为什么需要：飞书文档正文不应包含本地同步元数据。这些内容是本地专用的
（绑定信息、批注快照、文档标题冗余），推到飞书会污染正文，且 YAML/HTML
注释在飞书后端会被破坏（工作法实验 #1、#8 已验证）。

剥离 5 类内容：
  1. YAML front matter（---...---）
  2. <!--feishu:comments ... --> 块（多行）
  3. 首行 `#` h1 标题（飞书文档标题栏已独立显示）
  4. h1 紧随的元数据 blockquote（含"变更编号""创建日期"等）
  5. 元数据 blockquote 后的 `---` 分隔线（如有）

本实现与 `skills/fei2md/scripts/strip_metadata.py` 行为完全一致（工作法 §2
三层自包含结构要求两个 skill 各自持有一份）。一致性由共享单元测试 +
行为一致性核对保证。

用法：
  python3 strip_metadata.py strip <file.md>              # 输出剥离后的内容到 stdout
  python3 strip_metadata.py strip <file.md> -o out.md    # 写入文件
  cat file.md | python3 strip_metadata.py strip -        # 从 stdin 读
  python3 strip_metadata.py read-token <file.md>         # 读 feishu-doc wiki token
"""

import argparse
import sys
from pathlib import Path


def strip_local_metadata(content: str) -> str:
    """剥离本地元数据，返回干净的正文。

    Args:
        content: 原始 markdown 全文（含 front matter 等）。

    Returns:
        剥离 5 类本地元数据后的正文。保留正文内的所有真实内容、
        受保护元素标记（<!--feishu:whiteboard/image-->）、白板占位符。
        这些受保护标记的剥离由 clean_copy.py 负责，不在本函数。
    """
    lines = content.splitlines()

    # Step 1: 剥离 YAML front matter（首个 --- 到第二个 ---）
    lines = _strip_front_matter(lines)

    # Step 2: 剥离 <!--feishu:comments ... --> 块（多行，从起始标记到 -->）
    lines = _strip_comments_block(lines)

    # Step 3-5: 剥离首行 h1 + 元数据 blockquote + 其后分隔线
    lines = _strip_h1_and_metadata(lines)

    return "\n".join(lines).strip() + "\n"


def _strip_front_matter(lines: list) -> list:
    """剥离开头的 YAML front matter。

    front matter 格式：首行 --- 开头，到下一个 --- 结束。
    仅当文件以 --- 开头时才触发（避免误删正文里的分隔线）。
    """
    if not lines or not lines[0].strip().startswith("---"):
        return lines

    # 找第二个 ---（front matter 结束）
    for i in range(1, len(lines)):
        if lines[i].strip() == "---" or lines[i].strip().startswith("---"):
            # 返回 front matter 之后的内容（跳过结束的 ---）
            return lines[i + 1:]

    # 只有起始 --- 没有结束 ---，异常情况，原样返回
    return lines


def _strip_comments_block(lines: list) -> list:
    """剥离 <!--feishu:comments ... --> 多行块。

    从 `<!--feishu:comments` 起始行，到第一个 `-->` 结束行（含）。
    通常位于文件末尾，但代码不假设位置。
    """
    result = []
    in_comments = False
    for line in lines:
        stripped = line.strip()
        if not in_comments:
            if stripped.startswith("<!--feishu:comments"):
                in_comments = True
                continue  # 跳过起始行
            result.append(line)
        else:
            # 在 comments 块内，寻找结束标记
            if "-->" in line:
                in_comments = False
                continue  # 跳过结束行
            # 块内行直接丢弃
    return result


def _strip_h1_and_metadata(lines: list) -> list:
    """剥离首行 h1 标题 + 紧随的元数据 blockquote + 其后分隔线。

    仅剥离【正文开头】的 h1 和元数据 blockquote，不触碰正文中间的标题。
    元数据 blockquote 判定：h1 后紧跟的、以 > 开头的连续行。
    """
    # 跳过开头的空行，定位第一个非空行
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1

    if idx >= len(lines):
        return lines

    # 第一个非空行必须是 h1（单个 # 开头，非 ##）
    first = lines[idx].strip()
    if not (first.startswith("# ") and not first.startswith("## ")):
        return lines  # 开头不是 h1，不剥离

    # 跳过 h1，继续找元数据 blockquote
    idx += 1
    # 跳过 h1 后的空行
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1

    # 剥离紧随的元数据 blockquote（连续 > 开头的行）
    while idx < len(lines) and lines[idx].lstrip().startswith(">"):
        idx += 1

    # 剥离 blockquote 后的 --- 分隔线（如有，工作法规则 2 第 5 条）
    # 跳过空行后遇到 --- 才算
    check_idx = idx
    while check_idx < len(lines) and lines[check_idx].strip() == "":
        check_idx += 1
    if check_idx < len(lines) and lines[check_idx].strip() == "---":
        idx = check_idx + 1

    return lines[idx:]


def read_feishu_token(file_path: str) -> str:
    """从 markdown 文件 front matter 读 feishu-doc（wiki token）。

    统一的绑定信息读取入口，供 SKILL.md Step 1 调用。

    Raises:
        ValueError: 文件无 front matter 或缺 feishu-doc 字段。
        FileNotFoundError: 文件不存在。
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")

    content = path.read_text(encoding="utf-8")
    # 容错 BOM 和前置空行
    content = content.lstrip("\ufeff")
    lines = content.splitlines()
    # 跳过开头的空行
    first_non_empty = 0
    while first_non_empty < len(lines) and not lines[first_non_empty].strip():
        first_non_empty += 1

    if first_non_empty >= len(lines) or not lines[first_non_empty].strip().startswith("---"):
        raise ValueError(
            f"文件 {file_path} 无 front matter。请在文件开头添加：\n\n"
            f"---\nfeishu-doc: <wiki_token>\nfeishu-title: \"文档标题\"\n---"
        )

    for line in lines[1:]:
        if line.strip().startswith("---"):
            break  # front matter 结束
        if line.strip().startswith("feishu-doc:"):
            token = line.split(":", 1)[1].strip().strip('"').strip("'")
            if token:
                return token

    raise ValueError(
        f"文件 {file_path} 的 front matter 缺少 feishu-doc 字段。\n"
        "feishu-doc 是绑定飞书 wiki 文档的 wiki token（URL 中 wiki/ 后的部分）。"
    )


def main():
    parser = argparse.ArgumentParser(
        description="推送飞书前剥离本地元数据（工作法规则 2），或读取绑定 token"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # 剥离元数据
    p_strip = sub.add_parser("strip", help="剥离本地元数据")
    p_strip.add_argument("file", help="markdown 文件路径，或 - 从 stdin 读")
    p_strip.add_argument("-o", "--output", help="输出文件路径（默认 stdout）")

    # 读取 feishu-doc token
    p_token = sub.add_parser("read-token", help="从 front matter 读 feishu-doc wiki token")
    p_token.add_argument("file", help="markdown 文件路径")

    args = parser.parse_args()

    if args.cmd == "read-token":
        try:
            token = read_feishu_token(args.file)
            print(token)
        except (ValueError, FileNotFoundError) as e:
            print(f"错误：{e}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "strip":
        if args.file == "-":
            content = sys.stdin.read()
        else:
            path = Path(args.file)
            if not path.exists():
                print(f"错误：文件不存在：{path}", file=sys.stderr)
                sys.exit(1)
            content = path.read_text(encoding="utf-8")

        cleaned = strip_local_metadata(content)

        if args.output:
            Path(args.output).write_text(cleaned, encoding="utf-8")
            print(f"✅ 已剥离元数据，写入 {args.output}", file=sys.stderr)
        else:
            sys.stdout.write(cleaned)


if __name__ == "__main__":
    main()
