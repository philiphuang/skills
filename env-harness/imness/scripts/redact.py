#!/usr/bin/env python3
"""redact.py — 采集层打码（写 raw 前执行）。

覆盖 4 类硬凭证：密码 / API Key 哈希 / 手机号 / IBOSS client_secret。
只挡硬凭证，保留客户企业名/内部代号/手机号主体（讨论主体）。
raw 永远只有打码版，不保留原始。

契约见 imness/SKILL.md 的 redact 段落。
"""
import re
import sys

# === 4 类硬凭证正则 ===
# 密码：pw:/passwd:/password:/密码: 后跟非空白 token（中英文冒号都匹配）
_PASSWORD = re.compile(r'(?i)(pw|passwd|password|密码)\s*[:：]\s*(\S+)')
# API Key 哈希：40+ 位连续小写十六进制（飞书 API Key/t-aunt 等哈希形态）
_APIKEY_HASH = re.compile(r'(?<![0-9a-fA-F])[a-f0-9]{40,}(?![0-9a-fA-F])')
# 手机号：1[3-9] 开头 11 位（前后不能是字母或数字，避免误切长串/ID；中文/标点相邻正常切）
_PHONE = re.compile(r'(?<![0-9a-zA-Z])1[3-9]\d{9}(?![0-9a-zA-Z])')
# IBOSS client_secret：client_secret: 后跟非空白 token
_IBOSS_SECRET = re.compile(r'(?i)client_secret\s*[:：]\s*(\S+)')


def _redact_phone(m: re.Match) -> str:
    """手机号保留前3后4：17815098135 → 178****8135"""
    num = m.group(0)
    return f'{num[:3]}****{num[-4:]}'


def redact(text: str) -> str:
    """对文本执行 4 类硬凭证打码。纯函数，幂等。

    幂等性：打码后的文本再过一次不产生二次变化（手机号打码后含 ****，
    不再匹配 11 位数字；其余类替换为 [REDACTED] 也不含原凭证形态）。
    """
    if not text:
        return text
    # 顺序：先打长串（API Key 哈希），避免手机号正则误切哈希片段
    text = _APIKEY_HASH.sub('[REDACTED-HASH]', text)
    text = _IBOSS_SECRET.sub(lambda m: m.group(0).split(m.group(1))[0] + '[REDACTED]', text)
    text = _PASSWORD.sub(lambda m: f'{m.group(0).split(m.group(2))[0]}[REDACTED]', text)
    text = _PHONE.sub(_redact_phone, text)
    return text


def main():
    """CLI: stdin → stdout。供 collect 脚本管道调用。"""
    data = sys.stdin.read()
    sys.stdout.write(redact(data))


if __name__ == '__main__':
    main()
