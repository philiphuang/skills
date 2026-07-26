#!/usr/bin/env python3
"""match_comments.py — 识别变更章节中哪些批注落在待修改文字上。

飞书评注使用 block_id + 文本内字符偏移双重锚定。若批注所引用的文字
（quote）正好在本次变更中被删除或修改，则同步后该批注在 UI 层不可见。

本脚本做文本级匹配：读入 `lark-cli drive +list-comments` 输出的 JSON，
与待变更的 markdown 章节（或 git diff 中删除的旧文本）比对，输出命中的
批注列表。命中即触发策略 D（保留原文 + block_insert_after 插入替代段落）。

用法：
  python3 match_comments.py \
    --comments ./_comments.json \
    --section ./_section.md \
    --out ./_comment_hits.json

  # 只读旧文本（被删除部分）可提高精度：
  python3 match_comments.py \
    --comments ./_comments.json \
    --section ./_old_section.md \
    --out ./_comment_hits.json

输入 JSON 格式（lark-cli drive +list-comments 输出）：
  {
    "data": {
      "items": [
        {"comment_id": "xxx", "quote": "被批注文字", "content_anchor_id": "blkcn...", ...}
      ]
    }
  }

输出 JSON 格式：
  [
    {"comment_id": "xxx", "quote": "被批注文字", "content_anchor_id": "blkcn...", ...}
  ]
"""

import argparse
import json
import sys
from pathlib import Path


def load_comments(path: str) -> list[dict]:
    """从 lark-cli 输出 JSON 中读取 comments 列表。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("data", {}).get("items", []) or data.get("items", []) or []
    if isinstance(data, list):
        return data
    return []


def load_section_text(path: str) -> str:
    """读取待变更章节文本。"""
    return Path(path).read_text(encoding="utf-8")


def match_comments(comments: list[dict], section_text: str) -> list[dict]:
    """返回 quote 出现在 section_text 中的批注列表。

    匹配规则：
    - 优先用 comment['quote']（飞书局部批注返回的原文引用）。
    - 如无 quote，尝试用 comment['content'] 中的纯文本（全文评论）。
    - 匹配大小写敏感，按子串匹配。若 quote 为空或仅空白，忽略。

    注意：这只是一个保守的启发式检测。quote 出现只说明批注落在该章节；
    是否真正“被修改”还需要结合 git diff 判断。实际工作流中，命中即可触发
    策略 D，由人工二次确认。
    """
    hits = []
    for c in comments:
        quote = c.get("quote") or ""
        if not quote.strip():
            # 全文评论没有 quote，尝试 content 文本
            content = c.get("content", {})
            if isinstance(content, dict):
                quote = content.get("text") or ""
            else:
                quote = str(content)
        if not quote.strip():
            continue
        if quote in section_text:
            hits.append(c)
    return hits


def main():
    parser = argparse.ArgumentParser(
        description="识别变更章节中命中的飞书批注（用于策略 D 决策）"
    )
    parser.add_argument("--comments", required=True, help="lark-cli drive +list-comments 输出 JSON")
    parser.add_argument("--section", required=True, help="待变更章节 markdown 文件路径")
    parser.add_argument("--out", default="-", help="输出 JSON 路径（默认 - 表示 stdout）")
    args = parser.parse_args()

    comments = load_comments(args.comments)
    section_text = load_section_text(args.section)
    hits = match_comments(comments, section_text)

    output = json.dumps(hits, ensure_ascii=False, indent=2)
    if args.out == "-":
        sys.stdout.write(output + "\n")
    else:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"✅ 命中 {len(hits)} 条批注，已写入 {args.out}")


if __name__ == "__main__":
    main()
