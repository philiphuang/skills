#!/usr/bin/env python3
"""report.py — 从知识库三来源提取候选任务 → 生成报告 + 飞书镜像。

三来源（去重合并，累积 sources）：
  1. raw/meetings/*.md 的「## 待办」段（含 todo_id 锚点，置信度 EXTRACTED）
  2. wiki/topics/*.md 的「## 待办」段（置信度 INFERRED）
  3. wiki/synthesis/sessions/*.md 的结晶任务（置信度 INFERRED）

详见 imness/SKILL.md report 段落。
"""
import os, re, sys, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 路径（与 common.sh 对齐）
SCRIPT_DIR = Path(__file__).parent.resolve()
IMNESS_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = IMNESS_DIR.parent
KNOWLEDGE_DIR = PROJECT_ROOT / 'knowledge'
WIKI_DIR = KNOWLEDGE_DIR / 'wiki'
REPORTS_DIR = PROJECT_ROOT / 'reports'


_ASSIGNEE_RE = re.compile(r'\s+@([^\s]+(?:\s+[A-Z]+\s*\w*)*)(?=\s|$)')


def _extract_assignee(raw: str) -> tuple[str, str]:
    """从待办正文末尾提取 @负责人。

    返回 (content, assignee)：assignee 为空时 content 原样返回。
    供 meetings / sources 两个来源共用，单一来源真相。
    """
    m = _ASSIGNEE_RE.search(raw)
    if not m:
        return raw, ''
    return raw[:m.start()].rstrip(), m.group(1).strip()


def extract_todos_from_meetings():
    """来源 1：raw/meetings 的待办（带 todo_id，置信度 EXTRACTED）"""
    meetings_dir = KNOWLEDGE_DIR / 'raw' / 'meetings'
    if not meetings_dir.exists():
        return []
    results = []
    for md in sorted(meetings_dir.glob('*.md')):
        # topic_slug 用文件名除 token 后缀外的部分（如 AI_HUB营销..._obcn → AI_HUB营销...）
        stem = md.stem
        # 去掉末尾的 _obcxxxxx token 段
        title = re.sub(r'_obc[a-z0-9]+$', '', stem)
        text = md.read_text()
        for line in text.split('\n'):
            m = re.match(r'^-\s*\[[ x]\]\s*(.+?)(?:\s*<!--\s*todo_id:(\d+)\s*-->)?\s*$', line)
            if not m:
                continue
            content, assignee = _extract_assignee(m.group(1).strip())
            todo_id = m.group(2)
            results.append({
                'content': content,
                'assignee': assignee,
                'confidence': 'EXTRACTED',
                'topic_slug': title,
                'sources': [f'会议:{title}'],
                'dedupe_key': f'tid:{todo_id}' if todo_id else f'mtg:{content[:40]}',
            })
    return results


def extract_todos_from_wiki_topics():
    """来源 2：wiki/topics 的 ## 待办 段（置信度 INFERRED）"""
    topics_dir = WIKI_DIR / 'topics'
    if not topics_dir.exists():
        return []
    results = []
    for md in sorted(topics_dir.glob('*.md')):
        topic = md.stem
        text = md.read_text()
        in_todo = False
        for line in text.split('\n'):
            if re.match(r'^##\s*待办', line.strip()):
                in_todo = True
                continue
            if in_todo and re.match(r'^##\s', line.strip()):
                break
            if in_todo:
                m = re.match(r'^-\s*\[[ x]\]\s*(.+)$', line.strip())
                if m:
                    content = m.group(1).strip()
                    results.append({
                        'content': content,
                        'assignee': '',
                        'confidence': 'INFERRED',
                        'topic_slug': topic,
                        'sources': [f'wiki:topics/{topic}'],
                        'dedupe_key': f'wiki:{content[:40]}',
                    })
    return results


def extract_todos_from_synthesis():
    """来源 3：wiki/synthesis/sessions 的结晶任务（置信度 INFERRED）"""
    sess_dir = WIKI_DIR / 'synthesis' / 'sessions'
    if not sess_dir.exists():
        return []
    results = []
    for md in sorted(sess_dir.glob('*.md')):
        session = md.stem
        text = md.read_text()
        for line in text.split('\n'):
            # 结晶任务常见形态：- 待办：xxx / - 行动：xxx / - [ ] xxx
            m = re.match(r'^-\s*(?:\[.\]\s*)?(?:待办|行动|TODO|Action)[:：]?\s*(.+)$', line.strip(), re.I)
            if m:
                content = m.group(1).strip()
                results.append({
                    'content': content,
                    'assignee': '',
                    'confidence': 'INFERRED',
                    'topic_slug': session,
                    'sources': [f'synthesis:{session}'],
                    'dedupe_key': f'syn:{content[:40]}',
                    'assignee_in_content': bool(re.search(r'@\S', content)),
                })
    return results


def extract_todos_from_sources():
    """来源 4：wiki/sources/*.md 的「候选任务」段。

    这是 sdyckjq ingest 产出的 source 页里的待办——ingest 把 raw 消化成
    source 页时，会在其中提取候选任务（带 todo_id 锚点，置信度 EXTRACTED）。
    本来源是 imness ↔ sdyckjq 协作的关键断点：ingest 写 source 页，report 读它。
    """
    sources_dir = WIKI_DIR / 'sources'
    if not sources_dir.exists():
        return []
    results = []
    for md in sorted(sources_dir.glob('*.md')):
        source_name = md.stem
        text = md.read_text()
        in_todo = False
        for line in text.split('\n'):
            # 匹配「候选任务」段（含「供 report 提取」后缀的也算）
            if re.match(r'^##\s*候选任务', line.strip()):
                in_todo = True
                continue
            if in_todo and re.match(r'^##\s', line.strip()):
                break
            if in_todo:
                m = re.match(r'^-\s*\[[ x]\]\s*(.+?)(?:\s*<!--\s*todo_id:(\S+)\s*-->)?\s*$', line.strip())
                if m:
                    content, assignee = _extract_assignee(m.group(1).strip())
                    todo_id = m.group(2)
                    results.append({
                        'content': content,
                        'assignee': assignee,
                        'confidence': 'EXTRACTED',
                        'topic_slug': source_name,
                        'sources': [f'source:{source_name}'],
                        'dedupe_key': f'tid:{todo_id}' if todo_id else f'src:{content[:40]}',
                    })
    return results


def dedupe_and_merge(all_tasks):
    """去重合并：同任务（content 相似）合并 sources，累积溯源。归属不确定进「待澄清」。"""
    merged = {}
    order = []
    for t in all_tasks:
        # 去重键：优先 todo_id，否则用 content 前 40 字符归一化
        key_norm = re.sub(r'\s+', '', t['content'][:40]).lower()
        key = t['dedupe_key'] if t['dedupe_key'].startswith('tid:') else f'c:{key_norm}'
        if key in merged:
            # 合并 sources，置信度取高的
            existing = merged[key]
            for s in t['sources']:
                if s not in existing['sources']:
                    existing['sources'].append(s)
            if t['confidence'] == 'EXTRACTED':
                existing['confidence'] = 'EXTRACTED'
        else:
            merged[key] = dict(t)
            order.append(key)
    return [merged[k] for k in order]


def auto_triage(tasks):
    """自动按负责人分流：我的 / 委派他人 / 待澄清。

    负责人匹配规则（#23：身份判定数据源全局合并自 config）：
    - assignee 含 config 任一实例的 my_aliases 或 my_id → 我的
    - assignee 非空但不匹配我 → 委派他人（待他人确认，不自动建任务）
    - 无负责人且置信度非 EXTRACTED → 待澄清
    - 无负责人但置信度 EXTRACTED → 待澄清（虽有证据但缺负责人，需人工指定）

    身份数据来自 config.py 的全局合并（所有渠道所有实例），不按来源实例判定
    （4 个来源里 3 个是 sdyckjq 产出、无法追溯 instance）。
    """
    # 全局合并所有渠道所有实例的 aliases + ids（#23 身份消费）
    import config
    my_ids = set(config.all_my_aliases() + config.all_my_ids())

    mine, delegated, ambiguous = [], [], []
    for t in tasks:
        assignee = t.get('assignee', '')
        # 检查是否"我的"
        is_mine = any(my_id in assignee for my_id in my_ids)

        if is_mine:
            mine.append(t)
        elif assignee:
            # 有负责人但不是我 → 委派他人
            delegated.append(t)
        else:
            # 无负责人 → 待澄清
            ambiguous.append(t)

    return mine, delegated, ambiguous


def generate_report(publish_feishu=False):
    """生成候选任务报告。publish_feishu=True 时发布飞书镜像。"""
    all_tasks = (extract_todos_from_meetings()
                 + extract_todos_from_wiki_topics()
                 + extract_todos_from_synthesis()
                 + extract_todos_from_sources())
    if not all_tasks:
        print('没有候选任务')
        return None

    tasks = dedupe_and_merge(all_tasks)
    mine, delegated, ambiguous = auto_triage(tasks)

    date_str = datetime.now(tz=timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    lines = [
        f'# 候选任务报告 · {date_str}',
        '',
        f'> 共 {len(tasks)} 个候选任务。',
        f'> 🔴 **我的** ({len(mine)}) | 🟡 **委派他人** ({len(delegated)}) | ⚪ **待澄清** ({len(ambiguous)})',
        f'> 我的任务：确认后建飞书任务；委派他人：通知对方确认；待澄清：需补充负责人信息。',
        '',
    ]

    # 辅助函数
    def topic_block(task_list, heading, badge):
        if not task_list:
            return
        lines.append(f'## {badge} {heading}')
        lines.append('')
        by_topic = {}
        for t in task_list:
            by_topic.setdefault(t['topic_slug'], []).append(t)
        for topic in sorted(by_topic.keys()):
            lines.append(f'### {topic}')
            lines.append('')
            for t in by_topic[topic]:
                assignee = f' · **@{t["assignee"]}**' if t['assignee'] else ''
                conf = t['confidence']
                src = ' · '.join(t['sources'])
                lines.append(f'- [ ] {t["content"]}{assignee} · `{conf}`')
                lines.append(f'  - 来源: {src}')
            lines.append('')

    topic_block(mine, '我的任务', '🔴')
    topic_block(delegated, '委派他人（待对方确认）', '🟡')

    if ambiguous:
        lines.append('## ⚪ 待澄清（缺负责人信息）')
        lines.append('')
        for t in ambiguous:
            src = ' · '.join(t['sources'])
            lines.append(f'- [ ] {t["content"]} · `{t["confidence"]}`')
            lines.append(f'  - 来源: {src}')
        lines.append('')

    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = REPORTS_DIR / f'{date_str}-candidate-tasks.md'
    report_path.write_text('\n'.join(lines))

    print(f'报告已生成: {report_path}')
    print(f'候选任务: {len(tasks)} 个 (我的 {len(mine)} / 委派 {len(delegated)} / 待澄清 {len(ambiguous)})')

    if publish_feishu:
        publish_to_feishu(report_path)
    return str(report_path)


def publish_to_feishu(report_path):
    """输出飞书镜像发布提示（单向只读）。

    实际发布由 agent 调用 md2feishu skill 或 lark-doc skill 完成（交互式，
    需选目标空间/文档）。本函数只打印发布指令，不自动调用（避免写操作误触发）。
    """
    print('\n飞书镜像发布（单向只读，手动触发）:')
    print(f'  调用 /md2feishu 发布: {report_path}')
    print(f'  或调用 /lark-doc 创建文档，content 来自该报告')
    print('  发布后建议把飞书 doc URL 回填到报告头部。')


if __name__ == '__main__':
    publish = '--feishu' in sys.argv
    generate_report(publish_feishu=publish)
