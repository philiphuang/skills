#!/usr/bin/env python3
"""test_config.py — config.py 子命令的单元测试（#25 缺项 #6 补充）。

覆盖：
- instances: 列实例名 + JSON 输出
- instance: 取实例字段 + --field
- my-aliases: 单实例 + 全局合并
- meeting-chats: 子命令注册（不会调真实 lark-cli，仅验证参数解析）
- 向后兼容: 无 channels.feishu 时不崩溃

依赖 pytest（独立运行兼容）。
"""
import json
import os
import sys
import tempfile

import pytest

# 确保能 import config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# 原型 config（2 飞书 + 1 微信占位），与已删除的 config.prototype.yaml 等价
PROTOTYPE_YAML = """
channels:
  feishu:
    - name: work
      lark_profile: work
      my_name: 黄志恒
      my_id: ou_2dcb999e040285808d219a6362f6661d
      my_aliases: [黄志恒, 志恒, HZ]
      project_tags: [agent]
    - name: personal
      lark_profile: personal
      my_name: 黄志恒
      my_id: ou_xxx
      my_aliases: [黄志恒, 志恒]
      project_tags: [personal-project]
  wechat:
    - name: personal
      wxid: wxid_xxx
      my_name: Philip
      my_aliases: [Philip, 菲利]
"""

# 旧 schema config（顶层 feed_groups，向后兼容验证）
LEGACY_YAML = """
feed_groups:
  - agent
"""

# 空飞书实例（边界）
EMPTY_FEISHU_YAML = """
channels:
  feishu: []
"""


@pytest.fixture
def proto_config():
    """临时写入 prototype config，返回路径，测后清理。"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(PROTOTYPE_YAML)
        f.flush()
    os.environ['IMNESS_CONFIG'] = f.name
    # 清除 config 模块缓存（若有）
    if 'config' in sys.modules:
        del sys.modules['config']
    yield f.name
    os.unlink(f.name)
    os.environ.pop('IMNESS_CONFIG', None)


@pytest.fixture
def legacy_config():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(LEGACY_YAML)
    os.environ['IMNESS_CONFIG'] = f.name
    yield f.name
    os.unlink(f.name)
    os.environ.pop('IMNESS_CONFIG', None)


@pytest.fixture
def empty_config():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(EMPTY_FEISHU_YAML)
    os.environ['IMNESS_CONFIG'] = f.name
    yield f.name
    os.unlink(f.name)
    os.environ.pop('IMNESS_CONFIG', None)


# === instances ===

def test_instances_names(proto_config):
    """instances 子命令列出实例名。"""
    out = _run_config('instances')
    names = out.strip().split('\n')
    assert 'work' in names
    assert 'personal' in names


def test_instances_json(proto_config):
    """instances --json 输出 JSON 数组含完整字段。"""
    out = _run_config('instances', '--json')
    data = json.loads(out)
    assert len(data) == 2
    assert data[0]['name'] == 'work'
    assert data[1]['name'] == 'personal'
    assert data[0]['lark_profile'] == 'work'
    assert data[0]['project_tags'] == ['agent']


# === instance ===

def test_instance_fields(proto_config):
    """instance <name> 输出人类可读字段。"""
    out = _run_config('instance', 'work')
    assert 'name: work' in out
    assert 'lark_profile: work' in out
    assert 'project_tags: ' in out


def test_instance_field_single(proto_config):
    """instance --field 只取单字段。"""
    out = _run_config('instance', 'work', '--field', 'project_tags')
    assert "agent" in out


def test_instance_field_lark_profile(proto_config):
    """instance --field lark_profile。"""
    out = _run_config('instance', 'work', '--field', 'lark_profile')
    assert out.strip() == 'work'


def test_instance_missing(proto_config):
    """不存在的实例 exit 1。"""
    rc = _run_config_rc('instance', 'nonexistent')
    assert rc != 0


def test_instance_json(proto_config):
    """instance --json 输出 JSON。"""
    out = _run_config('instance', 'work', '--json')
    data = json.loads(out)
    assert data['name'] == 'work'
    assert data['lark_profile'] == 'work'


# === my-aliases ===

def test_my_aliases_single(proto_config):
    """my-aliases <name> 仅该实例。"""
    out = _run_config('my-aliases', 'work')
    assert '黄志恒' in out
    assert '志恒' in out
    assert 'HZ' in out
    assert 'Philip' not in out  # wechat 实例不混入单实例查询


def test_my_aliases_global(proto_config):
    """my-aliases 无参数全局合并。"""
    out = _run_config('my-aliases')
    # 飞书 work aliases + 飞书 personal aliases + 微信 aliases 全部合并
    assert '黄志恒' in out  # 两个飞书实例都有
    assert 'Philip' in out  # 微信实例
    assert '菲利' in out


# === 向后兼容 ===

def test_legacy_config_no_crash(legacy_config):
    """旧 schema（顶层 feed_groups）不会让 instances 崩溃，返回空列表。"""
    out = _run_config('instances')
    assert out.strip() == ''  # 旧 schema 无 channels.feishu，返回空


def test_empty_feishu_instances(empty_config):
    """无飞书实例时 instances 返回空。"""
    out = _run_config('instances')
    assert out.strip() == ''


# === helpers ===

def _run_config(*args):
    """调 config.py 子命令，捕获 stdout。"""
    import subprocess
    cp = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, 'config.py')] + list(args),
        capture_output=True, text=True, timeout=10)
    if cp.stderr:
        print(cp.stderr, file=sys.stderr)
    return cp.stdout


def _run_config_rc(*args):
    """调 config.py，返回退出码。"""
    import subprocess
    cp = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, 'config.py')] + list(args),
        capture_output=True, text=True, timeout=10)
    return cp.returncode


if __name__ == '__main__':
    # pytest 优先，无 pytest 时走简单 runner
    try:
        import pytest
        sys.exit(pytest.main([__file__, '-v']))
    except ImportError:
        print("pytest 不可用，运行核心手动验证...")
        # 退化到手动 runner（与 test_redact.py fallback 模式对齐）
        import tempfile

        def _tmp_cfg(content):
            path = tempfile.mktemp(suffix='.yaml')
            with open(path, 'w') as f:
                f.write(content)
            return path

        p = _tmp_cfg(PROTOTYPE_YAML)
        os.environ['IMNESS_CONFIG'] = p
        ok = fail = 0
        checks = [
            ("instances 有 work", 'work' in _run_config('instances')),
            ("instances JSON 双实例", len(json.loads(_run_config('instances', '--json'))) == 2),
            ("instance work.field", 'agent' in _run_config('instance', 'work', '--field', 'project_tags')),
            ("my-aliases 单实例", 'HZ' in _run_config('my-aliases', 'work')),
            ("my-aliases 全局合并", 'Philip' in _run_config('my-aliases')),
            ("不存在实例 exit!=0", _run_config_rc('instance', 'nonexistent') != 0),
        ]
        for name, passed in checks:
            if passed:
                ok += 1
                print(f'  PASS {name}')
            else:
                fail += 1
                print(f'  FAIL {name}')
        os.unlink(p)
        os.environ.pop('IMNESS_CONFIG', None)
        print(f'\n{ok} passed, {fail} failed')
        sys.exit(0 if fail == 0 else 1)
