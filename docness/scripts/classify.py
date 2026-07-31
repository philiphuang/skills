"""Knowledge base classification using LLM.

本模块是 stub：build_classify_prompt() 产出分类 prompt，但 classify() 不直接调用
LLM，而是返回该 prompt + reason="requires_llm"。agent 拿到 prompt 后自行调用 LLM，
再用 parse_classify_response() 解析返回的 JSON。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


DEFAULT_CATEGORIES = [
    "会议纪要",
    "方案设计",
    "需求文档",
    "技术资料",
    "合同协议",
    "汇报材料",
    "参考资料",
    "客户提供",
    "其他",
]


def get_existing_categories(kb_dir: str | Path = "知识库") -> list[str]:
    kb = Path(kb_dir)
    if not kb.exists():
        return []
    return sorted(
        d.name for d in kb.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def build_classify_prompt(
    content: str,
    existing_categories: list[str],
    default_categories: list[str] = DEFAULT_CATEGORIES,
) -> str:
    all_categories = sorted(set(default_categories + existing_categories))
    cats_list = "\n".join(f"- {c}" for c in all_categories)

    return f"""分析以下 Markdown 内容，判断最合适的知识库分类。

可用分类：
{cats_list}

文档内容（前 2000 字）：
{content[:2000]}

请选择最匹配的一个分类。如果分类不明确或内容不属于任何现有分类，返回 "UNCERTAIN"。

回复格式（只用 JSON，不要解释）：
{{"category": "分类名", "reason": "一句话理由"}}"""


def parse_classify_response(response_text: str) -> dict:
    try:
        data = json.loads(response_text.strip())
    except json.JSONDecodeError:
        cleaned = response_text.strip().lstrip("```json").rstrip("```").strip()
        if not cleaned.startswith("{"):
            idx = cleaned.find("{")
            if idx >= 0:
                cleaned = cleaned[idx:]
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return {"category": "UNCERTAIN", "reason": "parse_error"}

    category = data.get("category", "UNCERTAIN")
    reason = data.get("reason", "")
    if category not in (set(DEFAULT_CATEGORIES) | {"UNCERTAIN"}):
        category = "UNCERTAIN"
    return {"category": category, "reason": reason}


def classify(
    content: str,
    existing_categories: list[str],
    default_categories: list[str] = DEFAULT_CATEGORIES,
) -> dict:
    prompt = build_classify_prompt(content, existing_categories, default_categories)
    return {
        "prompt": prompt,
        "category": "UNCERTAIN",
        "reason": "requires_llm",
    }


def main():
    """命令行入口：python3 -m scripts.classify <Markdown文件路径> [知识库目录]。

    读取文件内容，产出分类 prompt（JSON 含 prompt 字段）。
    agent 拿到 prompt 后自行调用 LLM，再用 parse_classify_response() 解析。
    """
    if len(sys.argv) < 2:
        print(
            "用法: python3 -m scripts.classify <Markdown文件路径> [知识库目录]\n"
            "知识库目录默认为 知识库/",
            file=sys.stderr,
        )
        sys.exit(2)

    md_path = sys.argv[1]
    kb_dir = sys.argv[2] if len(sys.argv) > 2 else "知识库"

    content = Path(md_path).read_text(encoding="utf-8")
    existing = get_existing_categories(kb_dir)
    result = classify(content, existing)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
