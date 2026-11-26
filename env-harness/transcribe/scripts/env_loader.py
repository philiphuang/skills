#!/usr/bin/env python3
"""env_loader.py — agent 中立的环境配置回退链（AGENTS.md「Skill 中立性与环境配置」）。

回退链：环境变量 > 项目根 `skills.env`（KEY=VALUE）> 失败。

- 路径可用 `SKILLS_ENV_FILE` 覆盖（测试/多环境用）；未设置时取当前工作目录
  （调用方的项目根）下的 `skills.env`。
- 文件缺失静默跳过；仅当环境变量与文件都取不到值时，`get_required` 才抛
  `MissingEnvError`，报错信息写明两个落点。
- 回退只读：文件值不写回 `os.environ`，不污染机器环境。
- 兼容 `export KEY=VALUE` 前缀与 `KEY="quoted value"` 引号；`#` 注释行跳过。
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_FILENAME = "skills.env"
PATH_OVERRIDE_VAR = "SKILLS_ENV_FILE"


class MissingEnvError(EnvironmentError):
    """环境变量与 skills.env 都取不到值。"""


def resolve_skills_env_path() -> Path:
    """skills.env 路径：SKILLS_ENV_FILE > 当前工作目录/skills.env。"""
    override = os.environ.get(PATH_OVERRIDE_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.cwd() / DEFAULT_FILENAME


def load_env_file(path: Path) -> dict[str, str]:
    """解析 KEY=VALUE 文件；缺失返回空 dict，不抛错。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    loaded: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        loaded[key] = value
    return loaded


def _lookup(name: str) -> str | None:
    # 环境值 strip 后为空（如空白串）视为未设置，继续走文件回退
    env_value = (os.environ.get(name) or "").strip()
    if env_value:
        return env_value
    file_values = load_env_file(resolve_skills_env_path())
    file_value = (file_values.get(name) or "").strip()
    return file_value or None


def get_required(name: str) -> str:
    """取必填配置：env > skills.env；双落点都取不到时抛 MissingEnvError。"""
    value = _lookup(name)
    if value is None:
        raise MissingEnvError(
            f"{name} 未配置。两个落点均未取到："
            f"1) 环境变量 {name}；"
            f"2) 配置文件 {resolve_skills_env_path()}。"
            f"后者为 KEY=VALUE 格式（不进 git 仓），"
            f"路径可用环境变量 {PATH_OVERRIDE_VAR} 覆盖。"
        )
    return value


def get_optional(name: str, default: str | None = None) -> str | None:
    """取可选配置：env > skills.env > default。"""
    value = _lookup(name)
    return value if value is not None else default
