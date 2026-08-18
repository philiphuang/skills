# frontmatter 行级解析（共用）。字段名 → 键名映射。
_FM_KEYS = {"status": "status", "source_chat": "source_chat",
            "doc_type": "doc_type", "url": "url"}


def parse_fm(text: str) -> dict:
    result = {}
    for line in text.split("\n"):
        for fm_key, key in _FM_KEYS.items():
            if line.startswith(f"{fm_key}:"):
                result[key] = line.split(":", 1)[1].strip()
    return result
