"""Docness 工作目录解析与幂等初始化。

职责（对应 issue #98）：
1. 定位项目说明文件（AGENTS.md / agents.md / CLAUDE.md / claude.md）
2. 解析其中 docness 工作区配置（`## Docness 工作目录` 章节的 YAML 块，`docness:` 键）
3. 项目已声明 → 遵循声明路径；未声明 → 在项目根目录初始化 知识库/收件箱/发件箱/工作台，
   并把配置写回项目说明文件
4. 幂等：重复运行不删除/覆盖已有目录，配置原地更新不产生重复章节

CLI:
    python3 -m scripts.init_workspace [项目根目录] [--instructions 文件] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

from .utils import ensure_dir

# 项目说明文件查找顺序：兼容 agents.md 与 CLAUDE.md 两种命名
PROJECT_INSTRUCTION_FILES = ["AGENTS.md", "agents.md", "CLAUDE.md", "claude.md"]
# 无任何说明文件时新建的文件名（现代 agent 生态通行命名）
DEFAULT_PROJECT_FILE = "AGENTS.md"

# 工作区目录：键为配置键，值为默认相对路径（相对工作区根）
WORKSPACE_DIR_KEYS = ["收件箱", "知识库", "工作台", "发件箱"]
DEFAULT_WORKSPACE_DIRS = {
    "收件箱": "收件箱",
    "知识库": "知识库",
    "工作台": "工作台",
    "发件箱": "发件箱",
    "logs": ".logs",
}
_CONFIG_KEYS = WORKSPACE_DIR_KEYS + ["logs", "root"]
SECTION_TITLE = "## Docness 工作目录"


def find_project_instructions(project_root: str | Path) -> Path | None:
    """按优先级返回项目说明文件路径；不存在返回 None。"""
    root = Path(project_root)
    for name in PROJECT_INSTRUCTION_FILES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def _parse_yaml_block(block: str) -> dict | None:
    """解析一个 YAML 代码块，若包含 docness 工作区配置则返回配置 dict。"""
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("docness"), dict):
        return data["docness"]
    # 兼容直接写四键的裸映射（不包 docness: 前缀）
    if any(key in data for key in WORKSPACE_DIR_KEYS):
        return data
    return None


def _find_config_blocks(text: str) -> list[tuple[int, int, dict]]:
    """定位文件中包含 docness 工作区配置的 YAML 代码块。

    Returns:
        [(起始行号, 结束行号, 配置 dict)]，行号为 0-based。
    """
    lines = text.splitlines()
    blocks: list[tuple[int, int, dict]] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            fence_info = stripped[3:].strip()
            lang = fence_info.split()[0] if fence_info else ""
            if lang in ("yaml", "yml", ""):
                start = i
                i += 1
                content: list[str] = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    content.append(lines[i])
                    i += 1
                end = i  # 结束围栏行号（未闭合时为 len(lines)）
                config = _parse_yaml_block("\n".join(content))
                if config is not None:
                    blocks.append((start, end, config))
            i += 1
        else:
            i += 1
    return blocks


_HEADING_RE = re.compile(r"^#{1,6}\s*Docness(?:\s+工作目录)?\s*$")


def _find_replacement_span(lines: list[str], start: int) -> int:
    """返回配置块替换跨度起点：若块上方紧邻 Docness 章节标题则从标题行开始替换。

    标题与围栏之间允许空行；有其他内容隔开时只替换代码块本身。
    """
    span_start = start
    j = start - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    if j >= 0 and _HEADING_RE.match(lines[j].strip()):
        span_start = j
    return span_start


def _sanitize_config(config: dict) -> dict:
    """只保留已知键、过滤空值，防止未知键污染工作区解析。"""
    cleaned: dict = {}
    for key in _CONFIG_KEYS:
        value = config.get(key)
        if value is None or isinstance(value, (list, dict)):
            continue
        text = str(value).strip()
        if text:
            cleaned[key] = text
    return cleaned


def load_workspace_config(
    project_root: str | Path,
    instructions_file: str | Path | None = None,
) -> tuple[dict | None, Path | None]:
    """读取项目说明文件中的 docness 工作区配置。

    Returns:
        (配置 dict | None, 配置文件 Path | None)。
        配置文件存在但无配置块时返回 (None, 配置文件)，调用方据此写回。
    """
    root = Path(project_root)
    if instructions_file is not None:
        target = Path(instructions_file)
        if not target.is_absolute():
            target = root / target
    else:
        target = find_project_instructions(root)

    if target is None or not target.is_file():
        return None, None

    blocks = _find_config_blocks(target.read_text(encoding="utf-8"))
    if not blocks:
        return None, target
    return _sanitize_config(blocks[0][2]), target


def _rel_or_abs(path: Path, base: Path) -> str:
    """优先返回相对 base 的相对路径；不在 base 下时返回绝对路径。"""
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def resolve_workspace(
    project_root: str | Path,
    instructions_file: str | Path | None = None,
) -> dict:
    """解析工作区，不创建目录、不写配置。

    Returns:
        dict 含 project_root / workspace_root / config_file / configured 及
        各工作区目录绝对路径（键：收件箱/知识库/工作台/发件箱/logs）。
    """
    root = Path(project_root).resolve()
    config, config_file = load_workspace_config(root, instructions_file)
    config = config or {}

    workspace_root = root
    root_value = config.get("root", "").strip()
    if root_value:
        p = Path(root_value).expanduser()
        workspace_root = (p if p.is_absolute() else root / p).resolve()

    dirs: dict[str, Path] = {}
    for key, default in DEFAULT_WORKSPACE_DIRS.items():
        value = (config.get(key) or default).strip()
        p = Path(value).expanduser()
        dirs[key] = (p if p.is_absolute() else workspace_root / p).resolve()

    return {
        "project_root": root,
        "workspace_root": workspace_root,
        "config_file": config_file,
        "configured": bool(config),
        **dirs,
    }


def _build_config_section(ws: dict) -> str:
    """生成可写回项目说明文件的配置章节（含 ```yaml 代码块）。"""
    root_rel = _rel_or_abs(ws["workspace_root"], ws["project_root"])
    dirs = {
        key: _rel_or_abs(ws[key], ws["workspace_root"])
        for key in DEFAULT_WORKSPACE_DIRS
    }
    doc = {"docness": {"root": root_rel, **dirs}}
    body = yaml.dump(
        doc, allow_unicode=True, default_flow_style=False, sort_keys=False
    ).strip()
    return f"{SECTION_TITLE}\n\n```yaml\n{body}\n```\n"


def write_config(
    project_root: str | Path,
    ws: dict,
    instructions_file: str | Path | None = None,
) -> Path:
    """把工作区配置写回项目说明文件。

    已有 docness 配置块 → 原地替换（幂等，不产生重复章节）；
    说明文件不存在 → 新建（默认 AGENTS.md）。
    """
    root = Path(project_root).resolve()
    if instructions_file is not None:
        target = Path(instructions_file)
        if not target.is_absolute():
            target = root / target
    else:
        target = find_project_instructions(root) or (root / DEFAULT_PROJECT_FILE)

    section = _build_config_section(ws)

    if target.is_file():
        text = target.read_text(encoding="utf-8")
        blocks = _find_config_blocks(text)
        if blocks:
            lines = text.splitlines()
            start, end, _ = blocks[0]
            span_start = _find_replacement_span(lines, start)
            updated = lines[:span_start] + section.splitlines() + lines[end + 1 :]
            target.write_text("\n".join(updated).rstrip("\n") + "\n", encoding="utf-8")
            return target
    else:
        text = ""
        target.parent.mkdir(parents=True, exist_ok=True)

    if text and not text.endswith("\n"):
        text += "\n"
    with target.open("a", encoding="utf-8") as f:
        if text:
            f.write("\n")
        f.write(section)
    return target


def init_workspace(
    project_root: str | Path,
    instructions_file: str | Path | None = None,
    dry_run: bool = False,
) -> dict:
    """幂等初始化工作区。

    - 已声明配置 → 遵循声明（仅补建缺失目录，不动已有内容）
    - 未声明 → 创建 知识库/收件箱/发件箱/工作台/.logs 并把配置写回项目说明文件
    - 重复运行 → 只 mkdir(exist_ok=True)，不删除/覆盖已有目录
    """
    ws = resolve_workspace(project_root, instructions_file)
    if dry_run:
        return ws

    for key in DEFAULT_WORKSPACE_DIRS:
        ensure_dir(ws[key])

    if not ws["configured"]:
        ws["config_file"] = write_config(ws["project_root"], ws, instructions_file)
        ws["configured"] = True
    return ws


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="解析/初始化 docness 工作区")
    parser.add_argument(
        "project_root",
        nargs="?",
        default=".",
        help="项目根目录（默认当前目录）",
    )
    parser.add_argument(
        "--instructions",
        default=None,
        help="指定项目说明文件（默认自动查找 AGENTS.md / agents.md / CLAUDE.md / claude.md）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只输出解析结果，不创建目录、不写配置",
    )
    args = parser.parse_args(argv)

    ws = init_workspace(args.project_root, args.instructions, dry_run=args.dry_run)
    payload = {
        "project_root": str(ws["project_root"]),
        "config_file": str(ws["config_file"]) if ws["config_file"] else None,
        "configured": ws["configured"],
        "workspace": {key: str(ws[key]) for key in DEFAULT_WORKSPACE_DIRS},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
