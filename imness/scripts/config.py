#!/usr/bin/env python3
"""config.py — imness config 的唯一读取入口（#22/#24）。

config schema（#22 冻结）::

    channels:
      feishu:
        - name: work              # 实例标识（同渠道内唯一，必填）
          lark_profile: work      # lark-cli profile 名（认证隔离，必填）
          my_name: 黄志恒         # 我的显示名（必填）
          my_id: ou_xxx           # 我的 ou_id（必填）
          my_aliases: [黄志恒, 志恒, HZ]   # 我的简称（必填，≥1）
          project_tags: [agent]   # 项目标签（必填，≥1，= 原 feed_groups）
      wechat:
        - name: personal          # 占位，采集未实现
          wxid: wxid_xxx
          my_name: Philip
          my_aliases: [Philip]

契约（#22）：四个子命令 + 两个全局合并函数（#23 身份消费用）。
common.sh / chat_tools.py / report.py 都调它，不再内联 pyyaml。
"""
import json
import os
import sys

try:
    import yaml
except ImportError:
    sys.exit('config.py 需要 pyyaml: pip install pyyaml')


def _config_path():
    """config.yaml 位置 = 本脚本上级目录（imness/config.yaml）。

    可被环境变量 IMNESS_CONFIG 覆盖（prototype 用 config.prototype.yaml 验证）。
    """
    env = os.environ.get('IMNESS_CONFIG')
    if env:
        return env
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'config.yaml')


def _load(path=None):
    path = path or _config_path()
    if not os.path.exists(path):
        sys.exit(f'config 不存在: {path}')
    with open(path) as f:
        return yaml.safe_load(f)


def _instances(cfg, channel='feishu'):
    """取某渠道全部实例列表（空则 []）。"""
    return (cfg.get('channels', {}) or {}).get(channel, []) or []


def _validate_feishu(inst):
    """飞书实例必填字段校验，缺则报明确错误（#22：不静默降级）。"""
    required = ['name', 'lark_profile', 'my_name', 'my_id', 'my_aliases', 'project_tags']
    for k in required:
        if not inst.get(k):
            sys.exit(f"飞书实例 {inst.get('name', '?')} 缺必填字段: {k}")
    if not isinstance(inst['my_aliases'], list) or not inst['my_aliases']:
        sys.exit(f"飞书实例 {inst['name']} 的 my_aliases 必须是非空列表")
    if not isinstance(inst['project_tags'], list) or not inst['project_tags']:
        sys.exit(f"飞书实例 {inst['name']} 的 project_tags 必须是非空列表")


# === 子命令 ===

def cmd_instances():
    """instances [--channel feishu] [--json] → 列渠道下所有实例名或完整对象。"""
    args = _parse_flags(['--channel', '--json'])
    channel = args.get('--channel', 'feishu')
    as_json = '--json' in args
    insts = _instances(_load(), channel)
    if channel == 'feishu':
        for i in insts:
            _validate_feishu(i)
    if as_json:
        print(json.dumps(insts, ensure_ascii=False))
    else:
        for i in insts:
            print(i['name'])


def cmd_instance():
    """instance <name> [--channel feishu] [--field <f>] [--json] → 取实例完整字段。

    --field 只取某字段（如 project_tags），否则输出完整对象。
    """
    positional, flags = _parse_positional_and_flags(['--channel', '--field', '--json'])
    if not positional:
        sys.exit('用法: instance <name> [--channel feishu] [--field <f>] [--json]')
    name, channel = positional[0], flags.get('--channel', 'feishu')
    inst = _find_instance(name, channel)
    if '--field' in flags:
        print(inst.get(flags['--field'], ''))
    elif '--json' in flags:
        print(json.dumps(inst, ensure_ascii=False))
    else:
        # 人类可读多行
        for k, v in inst.items():
            print(f'{k}: {v}')


def cmd_my_aliases():
    """my-aliases [<instance_name>] → 输出当前实例或全局合并的 my_aliases（空格分隔）。

    无实例名 → 合并所有渠道所有实例（#23 身份消费全局合并用）。
    有实例名 → 仅该实例的 aliases。
    """
    positional, _ = _parse_positional_and_flags([])
    if positional:
        inst = _find_instance(positional[0], 'feishu')
        aliases = inst.get('my_aliases', [])
    else:
        # 全局合并所有渠道
        cfg = _load()
        aliases = []
        for channel_insts in ((cfg.get('channels', {}) or {}).values()):
            for i in channel_insts:
                aliases.extend(i.get('my_aliases', []) or [])
    print(' '.join(aliases))


# === #23 身份消费用的全局合并函数（供 report.py import）===

def all_my_aliases():
    """全局合并所有渠道所有实例的 my_aliases（report.py auto_triage 用）。"""
    cfg = _load()
    out = []
    for channel_insts in ((cfg.get('channels', {}) or {}).values()):
        for i in channel_insts:
            out.extend(i.get('my_aliases', []) or [])
    return out


def all_my_ids():
    """全局合并所有渠道所有实例的 my_id（report.py auto_triage 用）。"""
    cfg = _load()
    out = []
    for channel_insts in ((cfg.get('channels', {}) or {}).values()):
        for i in channel_insts:
            if i.get('my_id'):
                out.append(i['my_id'])
    return out


def get_instance(name, channel='feishu'):
    """取实例 dict（chat_tools.py / common.sh import 用）。"""
    return _find_instance(name, channel)


# === 内部 ===

def _find_instance(name, channel='feishu'):
    insts = _instances(_load(), channel)
    for i in insts:
        if i.get('name') == name:
            if channel == 'feishu':
                _validate_feishu(i)
            return i
    sys.exit(f'未找到 {channel} 实例: {name}')


def _parse_flags(flag_names):
    """无 positional 的简单 flag 解析。返回 {flag: value}（无值的 flag 值为 None，键存在即代表传入）。"""
    out = {}
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        a = args[i]
        if a in flag_names:
            if i + 1 < len(args) and not args[i + 1].startswith('--'):
                out[a] = args[i + 1]
                i += 2
            else:
                out[a] = None
                i += 1
        else:
            i += 1
    return out


def _parse_positional_and_flags(flag_names):
    """positional 与带值 flag 分开解析。"""
    positional = []
    flags = {}
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        a = args[i]
        if a in flag_names:
            flags[a] = args[i + 1] if i + 1 < len(args) else ''
            i += 2
        else:
            positional.append(a)
            i += 1
    return positional, flags


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('用法: config.py {instances|instance|my-aliases} [...]')
    cmd = sys.argv[1]
    {
        'instances': cmd_instances,
        'instance': cmd_instance,
        'my-aliases': cmd_my_aliases,
    }.get(cmd, lambda: sys.exit(f'未知子命令: {cmd}'))()
