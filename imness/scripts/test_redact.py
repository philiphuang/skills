#!/usr/bin/env python3
"""test_redact.py — redact() 纯函数单测（pytest 格式，保留 __main__ 独立运行）。

4 类硬凭证各覆盖正例（应打码，含中英文冒号）+ 反例（不应打码）+ 幂等性。

运行方式：
  pytest:    pytest products/imness/scripts/test_redact.py
  独立运行:  python3 products/imness/scripts/test_redact.py
"""
import sys
import os
import types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from redact import redact

# pytest 可能不存在（部署环境只保证 python3），独立运行时用裸 assert。
# 无 pytest 时构造一个 no-op 桩：parametrize 装饰器透传原函数，让 _run_standalone
# 能透过 .pytestmark 读取参数。
try:
    import pytest
except ImportError:
    class _NoPytest:
        class mark:
            @staticmethod
            def parametrize(_name, _values):
                def deco(fn):
                    fn.pytestmark = [types.SimpleNamespace(args=_values)]
                    return fn
                return deco
    pytest = _NoPytest()


# === 密码 ===

def test_password_english_colon_lower():
    assert redact('pw:gB2HQE2S') == 'pw:[REDACTED]'

def test_password_english_colon_upper():
    assert redact('PASSWORD:abc123') == 'PASSWORD:[REDACTED]'

def test_password_chinese_colon():
    assert redact('密码：xY9!k#z') == '密码：[REDACTED]'

def test_passwd_prefix():
    assert redact('passwd:secret') == 'passwd:[REDACTED]'

def test_password_in_sentence():
    assert redact('登录用 pw:gB2HQE2S 即可') == '登录用 pw:[REDACTED] 即可'

def test_password_noop_power():
    assert redact('power supply') == 'power supply'

def test_password_noop_no_colon():
    assert redact('password 字段') == 'password 字段'


# === API Key 哈希 ===

def test_apikey_standard():
    assert redact('d2fcb513a9e7c8d2f1b3a4c5d6e7f8a9b0c1d2e395ca') == '[REDACTED-HASH]'

def test_apikey_in_sentence():
    assert redact('token=d2fcb513a9e7c8d2f1b3a4c5d6e7f8a9b0c1d2e3') == 'token=[REDACTED-HASH]'

def test_apikey_noop_39_chars():
    assert redact('d2fcb513a9e7c8d2f1b3a4c5d6e7f8a9b0c1d2e') == 'd2fcb513a9e7c8d2f1b3a4c5d6e7f8a9b0c1d2e'

def test_apikey_noop_uppercase():
    assert redact('D2FCB513A9E7C8D2F1B3A4C5D6E7F8A9B0C1D2E3') == 'D2FCB513A9E7C8D2F1B3A4C5D6E7F8A9B0C1D2E3'

def test_apikey_noop_chinese():
    assert redact('广东高域科技有限公司') == '广东高域科技有限公司'


# === 手机号 ===

def test_phone_standard():
    assert redact('17815098135') == '178****8135'

def test_phone_in_sentence():
    assert redact('电话 17815098135 联系') == '电话 178****8135 联系'

def test_phone_noop_12_digits():
    assert redact('017815098135') == '017815098135'

def test_phone_noop_10_digits():
    assert redact('7815098135') == '7815098135'

def test_phone_noop_12_prefix():
    assert redact('12000000000') == '12000000000'

def test_phone_noop_adjacent_letter():
    assert redact('a17815098135') == 'a17815098135'


# === IBOSS client_secret ===

def test_iboss_english_colon():
    assert redact('client_secret:abc123XYZ') == 'client_secret:[REDACTED]'

def test_iboss_chinese_colon():
    assert redact('client_secret：xY9!k#z') == 'client_secret：[REDACTED]'

def test_iboss_noop_no_colon():
    assert redact('client_secret 字段') == 'client_secret 字段'


# === 幂等性 ===

@pytest.mark.parametrize('sample', [
    'pw:gB2HQE2S',
    '密码：xY9!k#z 电话 17815098135',
    'token=d2fcb513a9e7c8d2f1b3a4c5d6e7f8a9b0c1d2e395ca client_secret:foo',
    '正常文本无凭证 广东高域科技有限公司',
])
def test_idempotent(sample):
    once = redact(sample)
    assert redact(once) == once


# === 混合场景 ===

def test_mixed_all_credentials_redacted_subjects_preserved():
    mixed = ('周修捷: 邮箱密码 pw:gB2HQE2S, 电话 17815098135, '
             'API Key d2fcb513a9e7c8d2f1b3a4c5d6e7f8a9b0c1d2e395ca, '
             '客户 广东高域科技有限公司, client_secret:ibossXYZ')
    got = redact(mixed)
    # 各硬凭证都应被打码
    assert '[REDACTED]' in got
    assert '178****8135' in got
    assert '[REDACTED-HASH]' in got
    assert 'gB2HQE2S' not in got
    assert '17815098135' not in got
    # 讨论主体应保留
    assert '广东高域科技有限公司' in got
    assert '周修捷' in got


# === 独立运行入口（无 pytest 时也能跑：python3 test_redact.py）===

def _run_standalone():
    """无 pytest 环境下的极简 runner：收集所有 test_ 函数，裸 assert 失败即报错。"""
    pass_n, fail_n = 0, 0
    mod = sys.modules[__name__]
    # parametrize 在无 pytest 时手动展开
    import re as _re
    for name in sorted(dir(mod)):
        if not name.startswith('test_'):
            continue
        fn = getattr(mod, name)
        marks = getattr(fn, 'pytestmark', [])
        params = next((m.args for m in marks if hasattr(m, 'args')), None)
        if params:
            for sample in params:
                try:
                    fn(sample); pass_n += 1; print(f'  ✓ {name}[{sample[:20]!r}]')
                except AssertionError as e:
                    fail_n += 1; print(f'  ✗ {name}[{sample[:20]!r}] {e}')
        else:
            try:
                fn(); pass_n += 1; print(f'  ✓ {name}')
            except AssertionError as e:
                fail_n += 1; print(f'  ✗ {name} {e}')
    print(f'\n{"="*40}')
    print(f'结果: {pass_n} passed, {fail_n} failed')
    return 1 if fail_n else 0


if __name__ == '__main__':
    if pytest:
        sys.exit(pytest.main([__file__, '-v']))
    sys.exit(_run_standalone())
