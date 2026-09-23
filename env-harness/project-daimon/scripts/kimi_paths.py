#!/usr/bin/env python3
"""Kimi Desktop 沙箱路径的平台映射（唯一权威定义，#5）。

setup_skillshare.py（skills 落点）与 mcp-bridge.py（runtime 落点）共用本模块，
沙箱根目录名只此一处——改根名只改 SANDBOX_DIRNAME。

平台依据：
  - darwin : ~/Library/Application Support/kimi-desktop（本机实测，原默认值）
  - win32  : %APPDATA%/kimi-desktop（官方论坛 Windows 用户目录实列；
             APPDATA 未设置时回退 ~/AppData/Roaming）
  - 其他   : ${XDG_DATA_HOME:-~/.local/share}/kimi-desktop（XDG 惯例。
             Kimi Desktop 无官方 Linux 版，此映射未经实测——装了先用
             --kimi-path 校正，确认后回写本模块）

daimon 共享区相对路径（实测 macOS）：
  - skills      : daimon-share/daimon/skills
  - runtime home : daimon-share/daimon/runtime/kimi-code/home
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SANDBOX_DIRNAME = "kimi-desktop"
DAIMON_ROOT = ("daimon-share", "daimon")


def sandbox_base(platform: str | None = None) -> Path:
    """Kimi Desktop 沙箱根目录（按平台选择，默认取当前平台）。"""
    p = platform or sys.platform
    if p == "darwin":
        return Path.home() / "Library" / "Application Support" / SANDBOX_DIRNAME
    if p == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / SANDBOX_DIRNAME
    # Linux 及其余平台：XDG data 惯例
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / SANDBOX_DIRNAME


def skills_dir(platform: str | None = None) -> Path:
    """Kimi Desktop 的 skills 安装目录（setup_skillshare 的默认 --kimi-path）。"""
    return sandbox_base(platform).joinpath(*DAIMON_ROOT, "skills")


def runtime_home(platform: str | None = None) -> Path:
    """Kimi Desktop 沙箱内 kimi-code 的 HOME（mcp-bridge 插件落点）。"""
    return (
        sandbox_base(platform)
        .joinpath(*DAIMON_ROOT, "runtime", "kimi-code", "home")
    )
