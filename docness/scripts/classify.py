"""Knowledge base classification using LLM."""

from __future__ import annotations

import json
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
