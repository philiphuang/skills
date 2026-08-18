#!/usr/bin/env python3
"""test_chat_tools.py — cmd_find_active() 纯函数单测。

覆盖:
- 无匹配文件 → 空行
- 只有旧约定文件 → 返回旧文件
- 只有新约定文件 → 返回最新的（月份后缀最大的）
- 新旧混合 → 返回最新的（新约定优先，因为 _2026-08 > _2026-03 > 无后缀）
- 排除 .bak-* 备份文件
- 空目录 → 空行
- 中文文件名正常排序

运行: pytest test_chat_tools.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest


def _touch(d, name):
    (Path(d) / name).touch()


def _find(transcripts_dir, file_prefix):
    from chat_tools import cmd_find_active
    import io
    old_argv = sys.argv
    old_stdout = sys.stdout
    try:
        sys.argv = ['chat_tools.py', 'cmd_find_active', str(transcripts_dir), file_prefix]
        sys.stdout = io.StringIO()
        cmd_find_active()
        return sys.stdout.getvalue().rstrip('\n')
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout


class TestFindActive:

    def test_no_match_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            assert _find(d, 'anything_xxx') == ''

    def test_empty_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            assert _find(d, 'chat_abc123') == ''

    def test_old_convention_only(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(d, 'test_chat_oc_12345678.md')
            assert _find(d, 'test_chat_oc_12345678') == 'test_chat_oc_12345678.md'

    def test_new_convention_single(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(d, 'test_chat_oc_12345678_2026-08.md')
            assert _find(d, 'test_chat_oc_12345678') == 'test_chat_oc_12345678_2026-08.md'

    def test_new_convention_returns_newest_month(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(d, 'test_chat_oc_12345678_2026-03.md')
            _touch(d, 'test_chat_oc_12345678_2026-07.md')
            _touch(d, 'test_chat_oc_12345678_2026-08.md')
            assert _find(d, 'test_chat_oc_12345678') == 'test_chat_oc_12345678_2026-08.md'

    def test_mixed_old_and_new_prefers_newer(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(d, 'test_chat_oc_12345678.md')
            _touch(d, 'test_chat_oc_12345678_2026-03.md')
            _touch(d, 'test_chat_oc_12345678_2026-07.md')
            assert _find(d, 'test_chat_oc_12345678') == 'test_chat_oc_12345678_2026-07.md'

    def test_excludes_backup_files(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(d, 'test_chat_oc_12345678.md')
            _touch(d, 'test_chat_oc_12345678.md.bak-20260803')
            _touch(d, 'test_chat_oc_12345678_2026-08.md.bak-xyz')
            _touch(d, 'test_chat_oc_12345678_2026-08.md')
            assert _find(d, 'test_chat_oc_12345678') == 'test_chat_oc_12345678_2026-08.md'

    def test_prefix_exact_not_partial(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(d, 'chat_A_oc_12345678.md')
            _touch(d, 'chat_B_oc_12abcdef.md')
            assert _find(d, 'chat_A_oc_12345678') == 'chat_A_oc_12345678.md'

    def test_chinese_filename(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(d, 'AI_Hub运营支撑群_oc_069ab3995_2026-07.md')
            _touch(d, 'AI_Hub运营支撑群_oc_069ab3995_2026-08.md')
            assert _find(d, 'AI_Hub运营支撑群_oc_069ab3995') == 'AI_Hub运营支撑群_oc_069ab3995_2026-08.md'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
