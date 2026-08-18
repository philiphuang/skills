"""读取 knowledge/mywork.config.md。向上查找 CLAUDE.md 定根目录。"""
import os, re
from pathlib import Path


def root() -> Path:
    env = os.environ.get("SKILLS_FACTORY_ROOT")
    if env:
        return Path(env)
    cur = Path(__file__).resolve().parent
    for _ in range(8):
        if (cur / "CLAUDE.md").exists() or (cur / "AGENTS.md").exists():
            return cur
        cur = cur.parent
    raise RuntimeError("找不到项目根，请设 SKILLS_FACTORY_ROOT")


_CONFIG_PATH = root() / "knowledge" / "mywork.config.md"
_GROUP_LINE = re.compile(r'^-\s*\*\*(.+?)\*\*\s*—\s*(high|low)\s*:\s*(.*)$')
_cache: tuple | None = None


def _parse() -> tuple[list[dict], list[str], list[str]]:
    global _cache
    if _cache is not None:
        return _cache
    if not _CONFIG_PATH.exists():
        _cache = ([], [], []); return _cache

    text = _CONFIG_PATH.read_text()
    groups, focus, ignored = [], [], []
    section = None
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("## 群组重要性"):
            section = "groups"; continue
        if s.startswith("## 当前工作"):
            section = "work"; continue
        if s in ("### 进行中", "### 不关注"):
            section = "focus" if "不" not in s else "ignored"; continue
        if s.startswith("## ") or s.startswith("# "):
            section = None; continue
        if section == "groups":
            m = _GROUP_LINE.match(s)
            if m:
                groups.append({"name": m.group(1).strip(),
                               "importance": m.group(2).strip(),
                               "reason": m.group(3).strip()})
        elif section == "focus" and s.startswith("- "):
            focus.append(s[2:].strip())
        elif section == "ignored" and s.startswith("- "):
            ignored.append(s[2:].strip())
    _cache = (groups, focus, ignored)
    return _cache


def group_important(chat_name: str) -> tuple[bool, str]:
    groups, _, _ = _parse()
    for g in groups:
        if g["name"] in chat_name:
            return g["importance"] == "high", g["reason"]
    return False, f"群「{chat_name}」未在配置中"


def full_config() -> str:
    return _CONFIG_PATH.read_text() if _CONFIG_PATH.exists() else ""
