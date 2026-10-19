"""两段式分类引擎（#109）：第一段关键词确定性匹配；第二段产 ai_prompt 交 automation
agent 判定，脚本不调模型——手跑时第二段跳过，可独立运行。"""
from __future__ import annotations

import json
from dataclasses import dataclass

HIGH, MEDIUM, LOW = "high", "medium", "low"


@dataclass(frozen=True)
class Decision:
    entry: dict | None      # projects-map 命中条目（None = 待分拣）
    matched_keyword: str | None
    confidence: str         # high | medium | low
    by: str                 # keyword | llm | none


NO_MATCH = Decision(entry=None, matched_keyword=None, confidence=LOW, by="none")


def keyword_match(title: str, projects: list[dict]) -> Decision:
    """第一段：标题含关键词。唯一命中 high；多条目命中按映射序取首 medium（#108 v1 规则）。"""
    hits: list[dict] = []
    first_kw: str | None = None
    for entry in projects:
        for kw in entry.get("keywords") or []:
            if kw and kw in (title or ""):
                hits.append(entry)
                if first_kw is None:
                    first_kw = kw
                break
    if not hits:
        return NO_MATCH
    confidence = HIGH if len(hits) == 1 else MEDIUM
    return Decision(entry=hits[0], matched_keyword=first_kw, confidence=confidence, by="keyword")


def build_ai_prompt(title: str, summary: str, projects: list[dict]) -> str:
    """第二段输入：agent 据此返回 JSON；LLM 只能从映射既有条目里选（#108/#109 边界）。"""
    lines = [
        "判断以下千问录音纪要属于哪个项目。只能从候选列表里选 id，都不属于则 project 填 null。",
        f"标题：{title}",
        f"摘要：{summary or '（无）'}",
        "候选项目：",
    ]
    for entry in projects:
        desc = entry.get("description") or ""
        kws = "、".join(entry.get("keywords") or [])
        line = f"- id={entry.get('id')} name={entry.get('name')} keywords={kws}"
        if desc:
            line += f" 说明：{desc}"
        lines.append(line)
    lines.append('只输出一行 JSON：{"project": "<id 或 null>", "reason": "<一句话理由>"}')
    return "\n".join(lines)


def parse_llm_decision(text: str, projects: list[dict]) -> Decision:
    """第二段输出解析：不合法 / null / 不在映射 → 待分拣（docness UNCERTAIN 哨兵语义）。"""
    try:
        obj = json.loads((text or "").strip())
        pid = obj.get("project")
    except (json.JSONDecodeError, AttributeError):
        return NO_MATCH
    for entry in projects:
        if pid and entry.get("id") == pid:
            return Decision(entry=entry, matched_keyword="llm", confidence=MEDIUM, by="llm")
    return NO_MATCH
