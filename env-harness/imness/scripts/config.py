#!/usr/bin/env python3
"""config.py — imness config 的唯一读取入口（#22/#24）。

config schema（#22 冻结）::

    channels:
      feishu:
        - name: work              # 实例标识（同渠道内唯一，必填）
          lark_profile: work      # lark-cli profile 名（认证隔离，必填）
          my_name: 张三           # 我的显示名（必填）
          my_id: ou_xxx           # 我的 ou_id（必填）
          my_aliases: [张三, 三, ZS]     # 我的简称（必填，≥1）
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

# config_loader 是工厂跨 skill 共享模块（transcribe/scripts/，#241 统一配置层）。
# 两种布局：工厂 products/env-harness/transcribe/；中央池 skills-src/transcribe/（平铺）。
# 探测到才挂 sys.path；独立安装（无兄弟 skill）时静默降级为直接读 YAML 文件。
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 兄弟层探测（跨 skill 共享 config_loader）：
# - 工厂布局 products/env-harness/imness/scripts → 兄弟层 = products/env-harness
# - 中央池平铺布局 skills-src/imness/scripts → 兄弟层 = skills-src
# 同为 scripts/ 上溯两层，两种布局一条链；候选内含 config_loader.py 才挂 sys.path
_SIBLING = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
for _cand in (os.path.join(_SIBLING, 'transcribe', 'scripts'),
              os.path.join(_SIBLING, 'env-harness', 'transcribe', 'scripts')):
    if os.path.isfile(os.path.join(_cand, 'config_loader.py')):
        if _cand not in sys.path:
            sys.path.insert(0, _cand)
        break
del _cand, _SIBLING

CONFIG_FILENAME = 'env-harness-config.yaml'
CONFIG_PATH_VAR = 'ENV_HARNESS_CONFIG_FILE'


def _harness_config_path():
    """统一配置文件路径：ENV_HARNESS_CONFIG_FILE > 项目根/env-harness-config.yaml。

    项目根解析与 project_root() 同源（IMNESS_PROJECT_ROOT > 脚本物理位置上溯）。
    """
    override = os.environ.get(CONFIG_PATH_VAR, '').strip()
    if override:
        return override
    return os.path.join(project_root(), CONFIG_FILENAME)


def _imness_section():
    """读 IMNESS_CHANNELS 平铺键（结构化键，只走 config 文件，不查环境变量）。

    IMNESS_CONFIG 桥：测试/特殊部署用旧式整文件（含 channels: 顶层结构）时，
    经该 env 指定文件并取其 channels 段——正式途径是统一 config 的平铺键。
    """
    bridge = os.environ.get('IMNESS_CONFIG')
    if bridge:
        try:
            with open(bridge) as f:
                return (yaml.safe_load(f) or {}).get('channels', {}) or {}
        except Exception:
            return {}
    try:
        import config_loader
        value = config_loader.get_raw('IMNESS_CHANNELS')
        return value if isinstance(value, dict) else {}
    except ImportError:
        # 独立安装：直接读 YAML 文件顶层键
        try:
            with open(_harness_config_path()) as f:
                value = (yaml.safe_load(f) or {}).get('IMNESS_CHANNELS')
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}


def project_root():
    """项目根：默认 = imness/ 上级；IMNESS_PROJECT_ROOT env 可覆盖。

    跨项目部署（代码在中央库 skills-src、数据在项目根）时，脚本物理位置
    上溯得到的是中央库所在仓，必须用 env 指向真实项目根。
    """
    env = os.environ.get('IMNESS_PROJECT_ROOT')
    if env:
        return os.path.abspath(env)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def kb_root():
    """库根（其下挂 raw/ + wiki/）的唯一裁决处。

    优先级：IMNESS_KB_ROOT env > config 的 IMNESS_KB_ROOT 平铺键 > 自动探测
    > 项目根/knowledge（旧默认）。声明为相对路径时以项目根为基准。除末尾
    旧默认外，代码任何地方不得再出现 knowledge 路径字面量。
    与 common.sh resolve_kb_root() 同构。
    """
    env = os.environ.get('IMNESS_KB_ROOT')
    if env:
        return os.path.abspath(env)
    declared = ''
    try:
        import config_loader
        declared = str(config_loader.get('IMNESS_KB_ROOT') or '')
    except ImportError:
        try:
            with open(_harness_config_path()) as f:
                declared = str((yaml.safe_load(f) or {}).get('IMNESS_KB_ROOT') or '')
        except Exception:
            declared = ''
    if declared:
        root = project_root()
        return os.path.normpath(declared if os.path.isabs(declared)
                                else os.path.join(root, declared))
    root = project_root()
    if os.path.isfile(os.path.join(root, '.wiki-schema.md')) and os.path.isdir(os.path.join(root, 'raw')):
        return root
    return os.path.join(root, 'knowledge')


def _load(path=None):
    """载 imness 配置体。

    正式形态：统一 config 的 IMNESS_CHANNELS 平铺键 → 包装回 {channels: ...}
    结构（子命令/消费函数沿用旧 shape，零改动）。
    桥形态：IMNESS_CONFIG 指定的整文件（含 channels: 顶层结构）。
    """
    if path is not None:
        if not os.path.exists(path):
            sys.exit(f'config 不存在: {path}')
        with open(path) as f:
            return yaml.safe_load(f)
    channels = _imness_section()
    if not channels:
        sys.exit(f'IMNESS_CHANNELS 未配置。落点: 项目根 {CONFIG_FILENAME} 的平铺键 '
                 f'IMNESS_CHANNELS（路径可用 {CONFIG_PATH_VAR} 覆盖；测试可用 IMNESS_CONFIG 指整文件）。')
    return {'channels': channels}


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
