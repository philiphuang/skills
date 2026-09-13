#!/bin/bash
# maintain.sh — 知识库自维护（lint 巡检 + 健康报告）
#
# 检查项：孤立页 / 断链 / 过时（>90天）/ frontmatter 完整性 / 置信度标签滥用。
# 置信度高的问题自动修复（孤立页补链接），低的列入 reports/{date}-maintenance.md 待人工。
#
# 三层自维护的第一/三层（写入时去重由 sdyckjq ingest 负责；查询时动态整理由 agent
# 自主行为负责，见 SKILL.md）。本脚本是定期后台巡检层。
#
# 详见 imness/SKILL.md maintain 段落。
set -eo pipefail
source "$(dirname "$0")/common.sh"

REPORT_FILE="$PROJECT_ROOT/reports/$(date +%Y-%m-%d)-maintenance.md"
mkdir -p "$PROJECT_ROOT/reports"

info "运行知识库健康检查: $WIKI_DIR"

# 单一 python 检查 + 自动修复 + 报告输出
python3 - "$WIKI_DIR" "$KNOWLEDGE_DIR" "$REPORT_FILE" <<'PYEOF'
import os, re, sys, time
from datetime import datetime, timezone, timedelta

WIKI = sys.argv[1]
KB = sys.argv[2]
REPORT = sys.argv[3]

now = time.time()
pages = {}          # page_name → {path, links[], backlinks[], mtime}
all_link_targets = set()

# === 收集所有页面和链接 ===
for root, dirs, files in os.walk(WIKI):
    for f in files:
        if not f.endswith('.md'):
            continue
        path = os.path.join(root, f)
        name = os.path.splitext(f)[0]
        text = open(path).read()
        mtime = os.path.getmtime(path)
        # wikilink: [[目标]] 或 [[目标|别名]] 或 [[relation::目标]]
        links = set()
        for m in re.findall(r'\[\[([^\]|#]+)', text):
            target = m.split('|')[0].strip()
            # 过滤 relation::target 形态
            if '::' in target:
                target = target.split('::')[-1].strip()
            if target:
                links.add(target)
        pages[name] = {'path': path, 'links': links, 'mtime': mtime,
                       'rel': os.path.relpath(path, WIKI)}
        all_link_targets.update(links)

# === 检查 1：孤立页（无入链，排除 index/purpose 和 sources 叶子页）===
# sources/ 下的页天生是叶子节点，靠 index.md 聚合，不要求 wiki 内部互链
index_path_for_links = os.path.join(KB, 'index.md')
index_links = set()
if os.path.exists(index_path_for_links):
    idx_text = open(index_path_for_links).read()
    for m in re.findall(r'\[\[([^\]|#]+)', idx_text):
        index_links.add(m.split('|')[0].strip())
sources_names = {name for name, info in pages.items()
                 if '/sources/' in info['rel'].replace(os.sep, '/')}
orphan_names = {name for name in pages
                if name not in all_link_targets
                and name not in index_links
                and name not in ('index', 'purpose')
                and name not in sources_names}
# 自动修复：孤立页置信度高 → 在 index.md 补链接（index 是安全聚合点）
auto_fixed = []
index_path = os.path.join(KB, 'index.md')
index_text = open(index_path).read() if os.path.exists(index_path) else '# 索引\n\n'
index_changed = False
for name in sorted(orphan_names):
    rel = pages[name]['rel']
    if f']({rel})' in index_text or f'[[{name}]]' in index_text:
        continue  # 已在 index
    # 补进 index
    index_text += f'\n- [[{name}]] ({rel})'
    auto_fixed.append(name)
    index_changed = True
if index_changed:
    open(index_path, 'w').write(index_text)

# === 检查 2：断链（链接指向不存在的页面）===
broken = []
for name, info in pages.items():
    for target in info['links']:
        if target not in pages:
            broken.append((name, target))

# === 检查 3：过时（>90 天未更新）===
stale = []
for name, info in pages.items():
    age = (now - info['mtime']) / 86400
    if age > 90:
        stale.append((info['rel'], int(age)))
stale.sort(key=lambda x: -x[1])

# === 检查 4：frontmatter 完整性 ===
fm_issues = []
for name, info in pages.items():
    text = open(info['path']).read()
    if not text.startswith('---'):
        continue
    parts = text.split('---', 2)
    if len(parts) < 3:
        continue
    fm = parts[1]
    for field in ['tags', 'created', 'updated']:
        if f'{field}:' not in fm:
            fm_issues.append(f"{info['rel']}: 缺 {field}")

# === 检查 5：置信度标签（[事实]/[推断]/[待核]/[过时]）使用统计 ===
label_counts = {'事实': 0, '推断': 0, '待核': 0, '过时': 0}
for name, info in pages.items():
    text = open(info['path']).read()
    for lbl in label_counts:
        label_counts[lbl] += len(re.findall(rf'\[{lbl}\]', text))

# === 生成报告 ===
date_str = datetime.now(tz=timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
lines = [
    f'# 知识库健康报告 · {date_str}',
    '',
    f'> 自动修复: {len(auto_fixed)} 个孤立页已补入 index.md',
    f'> 待人工: 断链 {len(broken)} / 过时 {len(stale)} / frontmatter 问题 {len(fm_issues)}',
    '',
    '## 自动修复（孤立页 → index.md）',
    '',
]
if auto_fixed:
    for n in auto_fixed:
        lines.append(f'- ✓ [[{n}]] 已补入 index.md')
else:
    lines.append('- 无孤立页需修复')

lines += ['', '## 断链（指向不存在的页面）', '']
if broken:
    for src, tgt in broken[:20]:
        lines.append(f'- `{src}` → [[{tgt}]] （目标不存在）')
    if len(broken) > 20:
        lines.append(f'- ... 共 {len(broken)} 条')
else:
    lines.append('- 无断链')

lines += ['', '## 过时页面（>90 天未更新）', '']
if stale:
    for rel, age in stale[:10]:
        lines.append(f'- {rel} ({age} 天)')
else:
    lines.append('- 无过时页面')

lines += ['', '## frontmatter 完整性', '']
if fm_issues:
    for i in fm_issues[:10]:
        lines.append(f'- {i}')
else:
    lines.append('- frontmatter 完整')

lines += ['', '## 置信度标签分布', '']
for lbl, cnt in label_counts.items():
    lines.append(f'- [{lbl}]: {cnt} 处')

open(REPORT, 'w').write('\n'.join(lines) + '\n')

# 控制台摘要
print(f'  孤立页: {len(orphan_names)} (自动修复 {len(auto_fixed)})')
print(f'  断链: {len(broken)}')
print(f'  过时: {len(stale)}')
print(f'  frontmatter 问题: {len(fm_issues)}')
print(f'  置信度: {label_counts}')
PYEOF

ok "维护完成，报告: $REPORT_FILE"
