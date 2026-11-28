#!/usr/bin/env python3
"""config_loader.py — env-harness 统一配置读取/状态写入层（issue #241）。

两类分离（spec .scratch/unified-skills-config/design.md §4，2026-11-27 定稿）：

- **静态配置** `env-harness-config.yaml`（项目根，YAML，人写机读）：
  顶层平铺键，键名＝环境变量名（跨 skill 共用天然成立）；
  回退链 环境变量 > config 平铺键 > 失败。
  - 路径可用 `ENV_HARNESS_CONFIG_FILE` 覆盖；
  - 文件缺失静默跳过；双落点都取不到时 `get_required` 抛 `MissingEnvError`，
    报错写明两个落点；
  - 回退只读：文件值不写回 `os.environ`；
  - 无过渡期：旧 env 文件格式与旧路径覆盖变量均不识别（从未实际使用过）。
- **运行时参数** `env-harness-state.ini`（项目根，INI＋原子写，机写机读）：
  - **平铺不分段**（裁定 2026-11-28）：单 `[state]` 段，键＝`<skill>.<key>`（如
    `docness.last_ingest`）；跨 skill 共享键（kb_root）无前缀、只存一份，杜绝重复；
  - **每个参数带说明**：`STATE_KEY_DOCS` 注册表给出已知键的一行中文说明，
    每次重写时以注释行落盘（注册表外的键裸写，不断写流程）；
  - 标量值自动类型推断（int > float > str）；list/dict 以 JSON 字面量存取；
  - 原子写（tempfile.mkstemp + os.replace），不留 .tmp 残件；
  - `get_state` / `set_state` 按 skill 前缀隔离——patch 不被原地修改（不可变纪律）；
  - `get_watermark`：水位缺失时返回**当前时间往前 60 分钟**（首跑默认水位，
    只算不写——落盘发生在真正运行后），水位一经写入以文件为准。
"""
from __future__ import annotations

import configparser
import json
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - 环境问题，非代码路径
    sys.exit("config_loader 需要 pyyaml: pip install pyyaml")

CONFIG_FILENAME = "env-harness-config.yaml"
STATE_FILENAME = "env-harness-state.ini"
STATE_SECTION = "state"
CONFIG_PATH_VAR = "ENV_HARNESS_CONFIG_FILE"
STATE_PATH_VAR = "ENV_HARNESS_STATE_FILE"

# 跨 skill 共享的 state 键：无前缀存取，全文件唯一一份（裁定 2026-11-28 摊平）
SHARED_STATE_KEYS = frozenset({"kb_root"})

# 已知键说明注册表：重写文件时逐键落一行注释（"每个参数要加上说明"）
STATE_KEY_DOCS: dict[str, str] = {
    "kb_root": "知识库根（绝对路径）——水位归属库标识，多库切换时据此判断水位是否仍有效",
    "docness.last_collect": "docness：最近一次收集时间（Unix 秒；水位防回退，首跑默认 now−3600）",
    "docness.last_convert": "docness：最近一次转换时间（Unix 秒；水位防回退，首跑默认 now−3600）",
    "docness.last_ingest": "docness：最近一次消化时间（Unix 秒；水位防回退，首跑默认 now−3600）",
    "imness.last_collect": "imness：最近一次采集时间（Unix 秒；水位防回退，首跑默认 now−3600）",
    "tencent_meeting_sync.last_run":
        "tencent-sync：上次同步基准时间（Unix 秒；水位防回退，首跑默认 now−3600）",
    "tencent_meeting_sync.meeting_ids":
        "tencent-sync：已处理会议 id（幂等键；JSON 数组，只留最近 500 条）",
    "tencent_meeting_sync.processed_record_file_ids":
        "tencent-sync：已处理录制文件 id（排错用；JSON 数组，只留最近 500 条）",
}

# 首跑默认水位：当前时间往前 60 分钟（裁定 2026-11-27）
DEFAULT_WATERMARK_LOOKBACK_SECONDS = 3600


class MissingEnvError(EnvironmentError):
    """环境变量与 config 文件都取不到值。"""


class ConfigFileError(EnvironmentError):
    """config 文件存在但解析失败（含路径信息）。"""


class StateFileError(EnvironmentError):
    """state 文件存在但解析失败。"""


def resolve_config_path() -> Path:
    """config 路径：ENV_HARNESS_CONFIG_FILE > 当前工作目录/env-harness-config.yaml。"""
    override = os.environ.get(CONFIG_PATH_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.cwd() / CONFIG_FILENAME


def resolve_state_path() -> Path:
    """state 路径：ENV_HARNESS_STATE_FILE > 当前工作目录/env-harness-state.ini。"""
    override = os.environ.get(STATE_PATH_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.cwd() / STATE_FILENAME


def load_config_file(path: Path) -> dict:
    """解析 YAML config；缺失返回空 dict；坏 YAML 抛 ConfigFileError。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigFileError(f"config 文件解析失败: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _as_str(value: object) -> str | None:
    """YAML 值转字符串：strip 后为空（含空白串）视为未设置。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _lookup(name: str) -> str | None:
    # 环境值 strip 后为空（如空白串）视为未设置，继续走文件回退（PR #236 语义）
    env_value = (os.environ.get(name) or "").strip()
    if env_value:
        return env_value
    return _as_str(load_config_file(resolve_config_path()).get(name))


def get(name: str) -> str | None:
    """取配置：env > config 平铺键；双落点都取不到返回 None。"""
    return _lookup(name)


def get_raw(name: str) -> object:
    """整读平铺键的嵌套值（如 IMNESS_CHANNELS 列表），原结构返回；缺失返回 None。

    结构化键豁免环境变量链（裁定 2026-11-27）：值为 list/dict 的键只走
    config 文件——"键名＝环境变量名"仅对标量键成立，列表塞环境变量无意义。
    """
    value = load_config_file(resolve_config_path()).get(name)
    if isinstance(value, (list, dict)):
        return value
    env_value = os.environ.get(name, "").strip()
    if env_value:
        return env_value
    return value


def get_required(name: str) -> str:
    """取必填配置：env > config 平铺键；双落点都取不到时抛 MissingEnvError。"""
    value = _lookup(name)
    if value is None:
        raise MissingEnvError(
            f"{name} 未配置。两个落点均未取到："
            f"1) 环境变量 {name}；"
            f"2) 配置文件 {resolve_config_path()} 的顶层键 {name}。"
            f"后者为 YAML 格式（键名即环境变量名，不进 git 仓），"
            f"路径可用环境变量 {CONFIG_PATH_VAR} 覆盖。"
        )
    return value


def _value_to_ini(value: object) -> str:
    """值 → INI 字符串：list/dict 存 JSON 字面量，其余 str()。"""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _value_from_ini(text: str) -> object:
    """INI 字符串 → 值：JSON 字面量还原结构；int > float > str 类型推断。"""
    stripped = text.strip()
    if stripped[:1] in ("[", "{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return text
    for cast in (int, float):
        try:
            return cast(stripped)
        except ValueError:
            continue
    return text


def _load_state_flat(path: Path) -> dict[str, object]:
    """读 INI state 为平铺 dict；文件缺失返回空 dict；坏文件抛 StateFileError。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise StateFileError(f"state 文件解析失败: {path}: {exc}") from exc
    if not parser.has_section(STATE_SECTION):
        return {}
    return {k: _value_from_ini(v) for k, v in parser.items(STATE_SECTION)}


def _write_state_flat(path: Path, flat: dict[str, object]) -> None:
    """平铺 dict 原子写为 INI：[state] 单段，每个已知键前置一行说明注释。

    排序：共享键在前（kb_root 归属标识），其余按键名字典序——文件内容稳定，
    便于 diff 与人工检视。注释中的 `#` 已滤除（INI 注释符）。
    """
    ordered = sorted(
        flat.items(),
        key=lambda kv: (0 if kv[0] in SHARED_STATE_KEYS else 1, kv[0]),
    )
    lines = [
        "# env-harness-state.ini —— 运行时参数（机写机读）",
        "# 平铺不分段（#241）；本文件由 config_loader 原子重写，勿手编键值",
        f"[{STATE_SECTION}]",
    ]
    for key, value in ordered:
        doc = STATE_KEY_DOCS.get(key)
        if doc:
            lines.append(f"# {doc.replace('#', '')}")
        lines.append(f"{key} = {_value_to_ini(value)}")
    payload = "\n".join(lines) + "\n"

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".state-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def get_state(skill: str) -> dict:
    """读 skill 的运行时键集：平铺文件中 `<skill>.` 前缀的键剥前缀返回。

    共享键（kb_root）不属于任何 skill，不在此返回（消除重复的第一落点）。
    文件/键缺失返回空 dict（不抛错）。
    """
    prefix = f"{skill}."
    return {
        key[len(prefix):]: value
        for key, value in _load_state_flat(resolve_state_path()).items()
        if key.startswith(prefix)
    }


def set_state(skill: str, patch: dict) -> None:
    """合并写运行时键集：原子写、patch 键加 `<skill>.` 前缀、patch 不被原地修改。

    - patch 与现有前缀键浅合并（新键覆盖旧键，其余保留）；其余键全部不动；
    - 写入走 tempfile.mkstemp + os.replace，不留 .tmp 残件；
    - 写失败抛错，原文件不半写。
    """
    path = resolve_state_path()
    flat = _load_state_flat(path)
    prefix = f"{skill}."
    new_flat = dict(flat)
    for key, value in dict(patch).items():
        # 共享键无前缀：跨 skill 只存一份（摊平裁定）
        flat_key = key if key in SHARED_STATE_KEYS else f"{prefix}{key}"
        new_flat[flat_key] = value
    _write_state_flat(path, new_flat)


def get_watermark(skill: str, key: str) -> float:
    """读水位：键缺失时返回当前时间往前 60 分钟（首跑默认，只算不写）。

    水位一经写入以文件为准；默认值不落盘，落盘发生在真正运行后的
    `set_state` 调用——首跑不产生 state 副作用。缺 `last_` 前缀的非水位键
    缺失时同样返回默认（消费方仅对 `last_*` 键取默认）。
    """
    value = get_state(skill).get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return time.time() - DEFAULT_WATERMARK_LOOKBACK_SECONDS


def advance_watermark(skill: str, key: str, value: object) -> bool:
    """写水位（防回退，ADR-0001）：新值 > 旧值时写入并返回 True。

    - 新值 ≤ 旧值：no-op 返回 False，文件不动——重复执行结果相同；
    - 键缺失：直接写入（首写）；
    - 非数值值：不适用防回退语义，直通 set_state（各 skill 自行校验）；
    - 刻意的回退（如 fetch 失败回滚游标）走 set_state，不经本函数。
    """
    current = get_state(skill).get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(current, (int, float)) and not isinstance(current, bool):
            if float(value) <= float(current):
                return False
    set_state(skill, {key: value})
    return True
