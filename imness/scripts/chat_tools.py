#!/usr/bin/env python3
"""chat_tools.py — 飞书会话采集工具函数，供 collect-chats.sh 调用。

迁移自 chat_logs/scripts/chat_tools.py，适配 imness：
- 去掉写死的 FEED_GROUP_ID（由 shell 层读 config.yaml 动态获取）
- cmd_normalize 集成 redact（写 raw 前打码）
- cmd_find_name 的「排除自己」逻辑保留（黄志恒 = 当前 lark 用户）

多实例支持（#24）：cmd_find_name / cmd_normalize / cmd_normalize_meeting /
cmd_update_index / cmd_get_cursor 均接受可选 `--instance <name>` 参数：
- 有 --instance：按该实例的 aliases 排除自己、写 source_channel/source_instance
  frontmatter、index 游标按实例隔离。
- 无 --instance：尝试取 config 首个实例的 aliases；config 不可用时不排除任何人
"""
import json, sys, os

# redact / config 同目录，import 之
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from redact import redact


def _parse_instance_arg(argv_start=2):
    """从 sys.argv 解析 `--instance <name>`。

    返回 (instance_name_or_None, positional[剩余位置参数])。
    向后兼容：无 --instance 时 instance 为 None。
    """
    args = sys.argv[argv_start:]
    instance = None
    positional = []
    i = 0
    while i < len(args):
        if args[i] == '--instance' and i + 1 < len(args):
            instance = args[i + 1]
            i += 2
        else:
            positional.append(args[i])
            i += 1
    return instance, positional


def _exclude_set(instance_name):
    """单聊辨认对方名时「排除自己」的名字集合。

    有 instance → 读该实例的 my_aliases + my_name（经 config.py）。
    无 instance → 尝试从 config 取首个 feishu 实例的 aliases；
    config 不可用或无实例 → 返回空集（无法判断时保守地不排除任何人）。
    """
    if instance_name:
        try:
            import config
            inst = config.get_instance(instance_name)
            return set(inst.get('my_aliases', []) + [inst.get('my_name', '')])
        except Exception:
            pass
    # 无 instance 时：取 config 首个 feishu 实例的 aliases
    try:
        import config
        cfg = config._load()
        insts = config._instances(cfg, 'feishu')
        if insts:
            return set(insts[0].get('my_aliases', []) + [insts[0].get('my_name', '')])
    except Exception:
        pass
    # config 完全不可用时：返回空集（不被要求时不做假设）
    return set()


def cmd_list():
    """解析 feed-group-list-item JSON，输出每行一个 chat 的 JSON"""
    data = json.load(sys.stdin)
    items = data.get('data', {}).get('items', [])
    for i in items:
        c = {'feed_id': i.get('feed_id', ''), 'chat_name': i.get('chat_name', ''),
             'feed_type': i.get('feed_type', 'chat')}
        print(json.dumps(c, ensure_ascii=False))

def cmd_parse_one():
    """解析单个 chat JSON → feed_id \n chat_name \n feed_type"""
    c = json.load(sys.stdin)
    print(c.get('feed_id', ''))
    print(c.get('chat_name', ''))
    print(c.get('feed_type', 'chat'))

def cmd_find_name():
    """从消息列表中找到对话对方的名字（排除自己）。

    [--instance <name>]：按该实例的 aliases + my_name 排除自己（#23/#24）。
    无 --instance：兜底排除 {'黄志恒'}（旧行为）。
    """
    instance, _ = _parse_instance_arg()
    exclude = _exclude_set(instance)
    data = json.load(sys.stdin)
    msgs = data.get('data', {}).get('messages', [])
    from collections import Counter
    names = Counter()
    for m in msgs:
        s = m.get('sender', {})
        name = s.get('name', '')
        if name and s.get('sender_type') == 'user':
            names[name] += 1
    # 排除自己（实例 aliases + my_name），选最频繁的对方名
    for name, _ in names.most_common():
        if name not in exclude and name != '未知':
            print(name)
            return
    print('未知')

def cmd_pull():
    """提取消息列表 JSON 数组"""
    data = json.load(sys.stdin)
    msgs = data.get('data', {}).get('messages', [])
    print(json.dumps(msgs, ensure_ascii=False))

def cmd_has_more():
    data = json.load(sys.stdin)
    print(data.get('data', {}).get('has_more', False))

def cmd_page_token():
    data = json.load(sys.stdin)
    print(data.get('data', {}).get('page_token', ''))

def cmd_get_cursor():
    """读某 feed_id 的增量游标。
    Usage: cmd_get_cursor <index_file> <feed_id> [--instance <name>]
    输出: count last_create_time（空格分隔，游标为空时 count=0）
    把 index schema 知识收拢于此，避免 bash 内联 python3 -c 重复。

    [--instance]：按 (instance, feed_id) 匹配（#24 游标隔离）。
    无 --instance：按 feed_id 匹配（旧行为）。
    """
    instance, positional = _parse_instance_arg()
    index_file, feed_id = positional[0], positional[1]
    count, last_ct = 0, ''
    if os.path.exists(index_file):
        idx = json.load(open(index_file))
        for c in idx.get('chats', []):
            if c.get('feed_id') == feed_id:
                # 有 instance 要求时，实例字段也要匹配（游标隔离）
                if instance and c.get('instance') != instance:
                    continue
                count = c.get('message_count', 0)
                last_ct = c.get('last_message', {}).get('create_time', '')
                break
    print(f'{count} {last_ct}')

def _is_iso_like(s):
    """粗判 create_time 是否为可字典序比较的数字日期串（如 '2026-07-30 15:50'）。
    排除 '未知时间' 等中文兜底值污染游标比较。"""
    return bool(s) and s[0:4].isdigit()


def cmd_normalize():
    """bold-speaker 格式归一化 + 集成打码。

    每条消息输出含 message_id 锚点的行（HTML 注释，不显眼但可解析），
    供跨次增量去重。消息正文在写入前调 redact()，挡 4 类硬凭证。
    计数基于已写入锚点的 message_id 数（与文件 msg_id 数口径一致，
    空正文消息不写锚点故不计入）。

    [--instance <name>]：文件头写 source_channel/source_instance frontmatter
    （#23 溯源标记，sdyckjq ingest 时自然继承）。无 --instance 不写。
    """
    instance, _ = _parse_instance_arg()
    msgs = json.load(sys.stdin)
    seen = set()
    lines = []
    # 溯源 frontmatter（#23）：写文件头，供 sdyckjq ingest + report sources 溯源
    if instance:
        lines.append('---')
        lines.append('source_channel: feishu')
        lines.append(f'source_instance: {instance}')
        lines.append('---')
        lines.append('')
    last_create_time = ''
    for m in msgs:
        mid = m.get('message_id', '')
        if mid in seen:
            continue
        s = m.get('sender', {})
        sn = redact(s.get('name', '未知'))
        ct = m.get('create_time', '') or '未知时间'
        mt = m.get('msg_type', 'text')
        c = m.get('content', '')
        if mt == 'image':
            c = c or '[图片]'
        elif mt == 'file':
            c = c or '[文件]'
        elif mt == 'sticker':
            c = '[表情]'
        elif mt == 'system':
            c = f'[系统消息] {c}'
        if not c or not c.strip():
            continue  # 空正文：不写锚点、不计入 seen（计数口径与锚点数一致）
        # 仅在确认写入后才登记 seen（空正文消息不计入计数）
        seen.add(mid)
        # 跟踪最大 create_time 作增量游标；只接受 ISO 数字串，排除中文兜底值污染
        if _is_iso_like(ct) and ct > last_create_time:
            last_create_time = ct
        c = redact(c)
        # message_id 锚点（HTML 注释，渲染时不可见，但 grep/解析可提取用于跨次去重）
        lines.append(f'<!-- msg_id:{mid} -->')
        lines.append(f'**{sn}** ({ct}):')
        lines.append(c)
        lines.append('')
    result = '\n'.join(lines)
    print(result)
    # 计数基于 seen（已写入锚点的 message_id 数），与 cmd_dedupe_merge 的 msg_id 口径一致
    print(f'MESSAGE_COUNT:{len(seen)}')
    if last_create_time:
        print(f'LAST_CREATE_TIME:{last_create_time}')


def cmd_dedupe_merge():
    """合并 raw 文件已有内容（stdin）与新内容（argv[2]），按 msg_id 去重 + 按 create_time 排序。

    Usage: cmd_dedupe_merge <new_file>
    stdin = 已有文件全文，argv[2] = 新拉取并 normalize 后的全文。
    两者都是含 `<!-- msg_id:xxx -->` 锚点的 bold-speaker 文本。
    按 msg_id 去重，再按 block 内的 create_time 升序排列（旧→新，timeline 顺时序），
    解决 lark 默认 desc 与跨次 merge 导致的乱序。

    frontmatter 保留（#25 修复 #24 发现的隐患）：parse_blocks 按锚点切分会
    丢掉首锚点前的 frontmatter。合并后从 existing（优先）或 new 重新提取
    frontmatter 前缀拼回输出开头，保证 source_channel/source_instance 不丢。
    """
    existing = sys.stdin.read()
    new = open(sys.argv[2]).read() if len(sys.argv) > 2 else ''

    import re

    def extract_frontmatter(text):
        """提取首行起的 --- ... --- frontmatter 块（含尾部空行），无则返回 ''。"""
        if not text.lstrip().startswith('---'):
            return ''
        m = re.match(r'---\n.*?\n---\n?', text.lstrip(), re.DOTALL)
        if not m:
            return ''
        return m.group(0) + '\n'

    # frontmatter 优先取 existing（首次写入后已固化），回退取 new
    frontmatter = extract_frontmatter(existing) or extract_frontmatter(new)

    def parse_blocks(text):
        """按 msg_id 锚点切分成 [(msg_id, create_time, block_text)]"""
        blocks = []
        seen = set()
        parts = re.split(r'(<!-- msg_id:[^>]+ -->)', text)
        current_anchor = None
        current_body = []
        for part in parts:
            m = re.match(r'<!-- msg_id:([^>]+) -->', part)
            if m:
                if current_anchor and current_anchor not in seen:
                    seen.add(current_anchor)
                    ct_match = re.search(r'\*\*.+?\*\* \(([^)]+)\):', ''.join(current_body))
                    ct = ct_match.group(1) if ct_match else ''
                    blocks.append((current_anchor, ct, ''.join(current_body)))
                current_anchor = m.group(1).strip()
                current_body = [part]
            else:
                if current_anchor is not None:
                    current_body.append(part)
        if current_anchor and current_anchor not in seen:
            ct_match = re.search(r'\*\*.+?\*\* \(([^)]+)\):', ''.join(current_body))
            ct = ct_match.group(1) if ct_match else ''
            blocks.append((current_anchor, ct, ''.join(current_body)))
        return blocks

    # 去重（保首次出现），再按 create_time 升序排（ISO 数字串可字典序比较）
    merged = {}
    for mid, ct, body in parse_blocks(existing) + parse_blocks(new):
        if mid not in merged:
            merged[mid] = (ct, body)
    # 按 create_time 排序；非 ISO（如 '未知时间'）排到末尾
    def sort_key(item):
        ct = item[1][0]
        return ct if _is_iso_like(ct) else '9999'
    ordered = sorted(merged.items(), key=sort_key)
    # frontmatter 拼回开头（修复 #24 发现的增量丢失隐患）
    print(frontmatter + ''.join(body for _, (_, body) in ordered), end='')
    print(f'\nDEDUPED_COUNT:{len(ordered)}', file=sys.stderr)

def cmd_update_index():
    """更新 index.json（含增量游标）
    Usage: cmd_update_index <feed_id> <display_name> <feed_type> <file_rel> <count> <index_file> <feed_group_id> [last_create_time] [--instance <name>]
    feed_group_id 由 shell 层读 config 动态获取后传入。
    last_create_time 是本次拉取消息中最大的 create_time（ISO 字符串），作为下次增量游标。
    [--instance]：写入 chats[].instance 字段（#24 游标隔离）；匹配键变为 (instance, feed_id)。
    """
    instance, positional = _parse_instance_arg()
    feed_id, display_name, feed_type, file_rel, count_str, index_file = \
        positional[0], positional[1], positional[2], positional[3], positional[4], positional[5]
    feed_group_id = positional[6] if len(positional) > 6 else ''
    last_create_time = positional[7] if len(positional) > 7 else ''
    count = int(count_str)
    idx = {}
    if os.path.exists(index_file):
        with open(index_file) as f:
            idx = json.load(f)
    from datetime import datetime, timezone, timedelta
    idx['updated_at'] = datetime.now(tz=timezone(timedelta(hours=8))).isoformat()
    if feed_group_id:
        idx['feed_group_id'] = feed_group_id
    chats = idx.get('chats', [])
    found = False
    for c in chats:
        # 有 instance 时按 (instance, feed_id) 匹配（游标隔离）；否则按 feed_id（旧行为）
        if c.get('feed_id') == feed_id:
            if instance and c.get('instance') != instance:
                continue
            c['display_name'] = display_name
            c['feed_type'] = feed_type
            c['file'] = file_rel
            c['message_count'] = count
            if instance:
                c['instance'] = instance
            if last_create_time:
                c['last_message'] = {'create_time': last_create_time}
            found = True
            break
    if not found:
        new_chat = {'feed_id': feed_id, 'display_name': display_name,
                    'feed_type': feed_type, 'file': file_rel,
                    'message_count': count}
        if instance:
            new_chat['instance'] = instance
        if last_create_time:
            new_chat['last_message'] = {'create_time': last_create_time}
        chats.append(new_chat)
    idx['chats'] = chats
    with open(index_file, 'w') as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)

def cmd_merge():
    """合并两个 JSON 数组: stdin 每两行为一对 existing + new"""
    existing_raw = sys.stdin.readline()
    new_raw = sys.stdin.readline()
    existing = json.loads(existing_raw)
    new = json.loads(new_raw)
    existing.extend(new)
    print(json.dumps(existing, ensure_ascii=False))


def cmd_normalize_meeting():
    """把 +detail 的 JSON 产物归一化成结构化 markdown。

    stdin = +detail 输出（含进度日志前缀，自动跳过非 JSON 行）。
    输出 = markdown 正文 + `MEETING_TOKEN:<token>` 计数行。
    结构：标题 → summary（结论）→ todos（待办）→ chapters（timeline）→ keywords。
    全文调 redact 打码。
    """
    raw = sys.stdin.read()
    # 跳过进度日志行，取第一个 { 开始的 JSON
    json_start = raw.find('\n{')
    if json_start == -1 and not raw.lstrip().startswith('{'):
        sys.stderr.write('未找到 JSON 输出\n')
        sys.exit(1)
    json_text = raw[json_start + 1:] if json_start != -1 else raw
    try:
        d = json.loads(json_text)
    except json.JSONDecodeError as e:
        sys.stderr.write(f'JSON 解析失败: {e}\n')
        sys.exit(1)

    minutes = d.get('data', {}).get('minutes', [])
    if not minutes:
        sys.stderr.write('无 minute 数据\n')
        sys.exit(1)

    m = minutes[0]
    token = m.get('minute_token', '')
    title = redact(m.get('title', '未知会议'))
    art = m.get('artifacts', {})
    summary = redact(art.get('summary', '') or '')
    todos = art.get('todos', []) or []
    chapters = art.get('chapters', []) or []
    keywords = art.get('keywords', []) or []

    instance, _ = _parse_instance_arg()
    lines = []
    # 溯源 frontmatter（#23）：与 cmd_normalize 对齐
    if instance:
        lines.append('---')
        lines.append('source_channel: feishu')
        lines.append(f'source_instance: {instance}')
        lines.append('---')
        lines.append('')
    lines.append(f'# {title}')
    lines.append('')
    lines.append(f'<!-- minute_token:{token} -->')
    lines.append(f'- note_id: {m.get("note_id", "")}')
    lines.append('')

    if summary:
        lines.append('## 会议总结')
        lines.append('')
        lines.append(summary)
        lines.append('')

    if todos:
        lines.append('## 待办')
        lines.append('')
        for t in todos:
            content = redact(t.get('content', ''))
            done = 'x' if t.get('is_done') else ' '
            tid = t.get('todo_id', '')
            lines.append(f'- [{done}] {content} <!-- todo_id:{tid} -->')
        lines.append('')

    if chapters:
        lines.append('## 时间线')
        lines.append('')
        for ch in chapters:
            ch_title = redact(ch.get('title', ''))
            ch_sum = redact(ch.get('summary_content', ''))
            start_ms = int(ch.get('start_ms', 0))
            stop_ms = int(ch.get('stop_ms', 0))
            def ms_to_str(ms):
                s = ms // 1000
                return f'{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}'
            lines.append(f'### [{ms_to_str(start_ms)} - {ms_to_str(stop_ms)}] {ch_title}')
            lines.append('')
            lines.append(ch_sum)
            lines.append('')

    if keywords:
        lines.append('## 关键词')
        lines.append('')
        lines.append('、'.join(redact(k) for k in keywords))
        lines.append('')

    print('\n'.join(lines))
    print(f'MEETING_TOKEN:{token}')

def cmd_find_active():
    """找指定会话的最新活跃文件（兼容新旧命名约定）。

    用法: python3 chat_tools.py cmd_find_active <transcripts_dir> <file_prefix>
    输出: 文件名（不含路径），无匹配时输出空行。

    匹配规则：
      - 新约定: {file_prefix}_{YYYY-MM}.md
      - 旧约定: {file_prefix}.md（无月份后缀，兼容已采集未迁移的旧文件）
      - 排除 .bak-* 备份文件
    选择: 按文件名倒序取最大——月份后缀大的自动排在前面。
    """
    import re

    transcripts_dir = sys.argv[2]
    file_prefix = sys.argv[3]

    pattern = re.compile(re.escape(file_prefix) + r'(?:_\d{4}-\d{2})?\.md$')

    candidates = []
    try:
        for f in os.listdir(transcripts_dir):
            if pattern.match(f) and '.bak-' not in f:
                candidates.append(f)
    except FileNotFoundError:
        pass

    if not candidates:
        print('')
        return

    candidates.sort(reverse=True)
    print(candidates[0])


if __name__ == '__main__':
    fn = sys.argv[1]
    globals()[fn]()
