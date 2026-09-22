#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_shaping.py — jf-interview 访谈产物（shaping/ 8 件套）校验门禁

校验 shaping 目录是否满足 jf-interview 定义的门禁（G1–G7）。契约全文见：
  products/jiaofu/jf-interview/references/shaping-contract.md

用法：
  python3 check_shaping.py <shaping目录> [--json]
  python3 check_shaping.py <shaping目录> --manifest <manifest.json>
  python3 check_shaping.py --self-test        # 内置样例断言（样例在 _selftest.py）

--manifest 给出时，G5 会把条目引用的页面 id 与 manifest.pages[].id 交叉校验
（jf-ia 的产物，schema 见 products/jiaofu/jf-contract/references/manifest-schema.md）；
条目没有页面 id 即判 ERROR——给了 manifest 就是要做页面级交叉校验，只靠 DR 编号
追溯等于把这项校验关掉。不给 --manifest 时按内置的文档名/skill 名黑名单排除，
并对形似页面 id 的排除项给 WARN。

退出码：
  0  通过（无 ERROR；WARN 仍算通过）
  1  未通过（存在 ERROR）
  2  用法错误 / 目录不存在 / manifest 不可读
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

SHAPING_FILES = [
    "00-intake.md",
    "01-problem.md",
    "02-users.md",
    "03-journey.md",
    "04-scope.md",
    "05-flows.md",
    "06-shaped-brief.md",
    "07-open-questions.md",
]

SCOPE_CATEGORIES = ("做", "暂缓", "不做", "待确认")

ERROR = "ERROR"
WARN = "WARN"

# 04-scope.md 四分类标题：##–#### 级，标题文本为分类词（可带「项/清单」等后缀与括号注释）
# 后缀是必要的：「## 待确认项」是常见写法，旧实现只认光秃秃的分类词，
# 于是报出「缺少「待确认」分类标题」——类别明明在，话术还说反了。
SCOPE_HEADING_RE = re.compile(
    r"^#{2,4}\s*(做|暂缓|不做|待确认)\s*"
    r"(?:项|事项|清单|列表|内容)?\s*(?:[（(][^）)]*[）)])?\s*$")
# 顶层列表项（无缩进）：无序 `- ` / `* ` / `+ `，或有序 `1. ` / `1、` / `1)`
# 有序列表必须有：把旅程分支或待确认写成编号清单是中文文档的常见写法，
# 只认 `- ` 会让整份分支无人校验（回测：8 个分支全改有序列表 → 门禁全绿）。
# `\d{1,3}` 而非 `\d+`：免得把行首的「2026. 08. 11」当成列表项。
TOP_ITEM_RE = re.compile(r"^(?:[-*+]\s+|\d{1,3}[.、)）]\s*)\S")
# 「分支：」的定义写法：用来揪出没被 TOP_ITEM_RE 认出来的分支（`### 分支：x`、
# 行首加粗的 `**分支：x**` 等）——认不出来就等于该分支无人校验，不能静默跳过。
# 判据是「分支 + 可选序号 + 冒号」而不是光有「分支」二字：主路径步骤里
# 「……两条候选分支见下」只是提到分支，不是分支定义，不能当分支校验。
BRANCH_DEF_RE = re.compile(r"分支\s*[0-9一二三四五六七八九十]*\s*[：:]")
# 07 条目锚：顶层列表项且含 OQ-编号 或 冲突 标记
ENTRY_ANCHOR_RE = re.compile(r"OQ-\d+|冲突[-：:]")
# OQ 编号 / 07 条目的「影响页面」字段
OQ_NUM_RE = re.compile(r"OQ-\d+")
PAGE_FIELD_RE = re.compile(r"影响页面\s*[:：]")
# 引用块前缀（G2 要求引用块也算内容，见 first_paragraph）
BLOCKQUOTE_PREFIX_RE = re.compile(r"^\s*>\s?")
# 页面 id：小写字母+数字+连字符，至少一个连字符（如 leader-review-list）
PAGE_ID_RE = re.compile(r"(?<![a-zA-Z0-9-])[a-z]+[a-z0-9]*(?:-[a-z0-9]+)+?(?![a-zA-Z0-9-])")
# 形似页面 id、实为文档名/脚本名的排除项：不计入 G5 的追溯依据。
# 背景：PAGE_ID_RE 本身匹配任意 kebab-case 英文词，写 open-questions / jf-prd
# 也能「通过」原本的 G5——黑名单把这类廉价满足堵掉（给了 --manifest 则直接查表）。
NON_PAGE_TOKENS = frozenset({
    # 本 skill 的脚本与契约/ schema 文档
    "check-shaping", "shaping-contract", "manifest-schema",
    # 8 件套文件名（已去掉序号与 .md，仅这两个带连字符）
    "open-questions", "shaped-brief",
})
# skill 名一律是 jf-<词>（jf-prd / jf-ia / jf-interview …），页面 id 不带 jf- 前缀；
# 用前缀规则兜底，免得每次新增 skill 都要回来补黑名单
JF_SKILL_RE = re.compile(r"^jf-[a-z0-9-]+$")
# G4 分支「用户看到什么」的同义词：中文里同一语义有多种写法，
# 只认「看到」会把「显示/呈现/展示」这类正确描写误判为 ERROR。
BRANCH_VISIBLE_WORDS = ("看到", "显示", "展示", "呈现", "出现", "弹出", "跳转到")
# MRD 的 DR 编号：DR: D-01 / D-01 / DR-1
DR_REF_RE = re.compile(r"(?:DR[-：:]?\s*)?D-\d+")
# 句末标点（G2 按。！？!? 切句）
SENTENCE_END_RE = re.compile(r"[。！？!?]+")
# 冲突字样（G6）——按句判定，四层规则见 find_conflict_markers()。
# 旧实现只有一个三词正则（口径冲突|两次口径|口径不一致），中文里换个说法就绕过去了
# （回测：「260811 与 260814 的说法对不上」+ 07 不单列 → 全绿）。
CLAUSE_SPLIT_RE = re.compile(r"[。；！？!?;\n]+")
LEGACY_CONFLICT_RE = re.compile(r"口径冲突|两次口径|口径不一致")
# 时间/双源信号：同一件事被说过两次的痕迹
CONFLICT_TEMPORAL_RE = re.compile(
    r"两次|前后|先前|原本|原来|起初|之前|后又|又改|改口|口径变|反口")
CONFLICT_TWO_SHOT_RE = re.compile(
    r"(?:原先|原来|起初|之前|早先)[^。；\n]{0,40}(?:现在|如今|后来)")
# 句内出现两个日期（YYMMDD 或 年-月-日）＝两个来源被摆在一起
CONFLICT_DATE_RE = re.compile(
    r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}|\d{6}")
CONFLICT_STRONG_RE = re.compile(
    r"冲突|矛盾|不一致|对不上|相左|有出入|改了|变了|改成|改为|变更为|调整为")
# 「不同 / 不一样」单独太弱（「对技术领域的要求不同」是正常描述），
# 只有同句还有主体词（口径/说法/要求…）时才算冲突信号
CONFLICT_WEAK_RE = re.compile(r"不同|不一样")
CONFLICT_SUBJECT_RE = re.compile(r"口径|说法|表述|要求|答复|定义|描述|结论")
# 冲突条目的原话子行：须带来源与时间点
YUANHUA_RE = re.compile(r"原话")
DATE_RE = re.compile(r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}")


class Issue:
    __slots__ = ("code", "level", "message")

    def __init__(self, code: str, level: str, message: str):
        self.code = code
        self.level = level
        self.message = message

    def as_dict(self):
        return {"code": self.code, "level": self.level, "message": self.message}

    def __str__(self):
        return "  [%s] %-4s %s" % (self.level, self.code, self.message)


class Report:
    def __init__(self):
        self.issues: list[Issue] = []

    def add(self, code, level, message):
        self.issues.append(Issue(code, level, message))

    def error(self, code, message):
        self.add(code, ERROR, message)

    def warn(self, code, message):
        self.add(code, WARN, message)

    @property
    def errors(self):
        return [i for i in self.issues if i.level == ERROR]

    @property
    def warnings(self):
        return [i for i in self.issues if i.level == WARN]


# --------------------------------------------------------------------------- #
# Markdown 解析（只用标准库正则，避免依赖 markdown 库）
# --------------------------------------------------------------------------- #

def read_text(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def split_sections(text: str):
    """按标题切段：返回 [(原始标题行或 None, [行...])]，标题行不含在内。"""
    sections = []
    cur_head, cur_lines = None, []
    for line in text.splitlines():
        if re.match(r"^#{1,6}\s+\S", line):
            sections.append((cur_head, cur_lines))
            cur_head, cur_lines = line, []
        else:
            cur_lines.append(line)
    sections.append((cur_head, cur_lines))
    return sections


def parse_blocks(lines):
    """把顶层列表切成 [(锚行, [后续缩进/空行...])]，非列表正文终止当前块。"""
    blocks = []
    anchor, body = None, []
    for line in lines:
        if TOP_ITEM_RE.match(line):
            if anchor is not None:
                blocks.append((anchor, body))
            anchor, body = line, []
        elif anchor is not None:
            if line.strip() == "" or line[:1] in (" ", "\t"):
                body.append(line)
            else:
                blocks.append((anchor, body))
                anchor, body = None, []
    if anchor is not None:
        blocks.append((anchor, body))
    return blocks


def _lines_outside_blocks(lines):
    """返回不属于任何「条目块」的行。

    条目块 = 顶层列表项（TOP_ITEM_RE）+ 其缩进/空行续行。落在这个范围外的行
    门禁看不见，用来检出「写成了分支、却没写成条目」的漏网写法。
    """
    inside, out = False, []
    for line in lines:
        if TOP_ITEM_RE.match(line):
            inside = True
        elif inside and (line.strip() == "" or line[:1] in (" ", "\t")):
            pass                      # 块内续行
        else:
            inside = False
            out.append(line)
    return out


def first_paragraph(text: str) -> str:
    """第一个非空、非标题/列表/表格/代码/注释的内容块（可跨物理行）。

    引用块（`> `）**算内容**。旧实现把它和标题一起跳过、继续往下找，于是 G2
    校验的是作者没打算当首段的那一段：回测里定位写成引用块 + 次段正常 → 0 error
    （假绿），定位写成引用块 + 次段 5 句 → 报错指向次段（假红）。两种都判错了对象。
    """
    markup = ("#", "-", "*", "+", "|", "```", "<!--")
    para, started = [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(">"):
            if started:               # 引用块是独立块，结束当前段落
                break
            s = BLOCKQUOTE_PREFIX_RE.sub("", s).strip()
        if not started:
            if not s or s.startswith(markup):
                continue
            para.append(s)
            started = True
        else:
            if not s or s.startswith(markup):
                break
            para.append(s)
    return "".join(para)


def count_sentences(paragraph: str) -> int:
    return len([s for s in SENTENCE_END_RE.split(paragraph) if s.strip()])


def find_conflict_markers(text: str):
    """返回 text 中疑似「同一件事两次口径不一致」的句子（G6 用）。

    一个句子命中任一条件即算冲突信号：
      1. 历史三词（口径冲突 / 两次口径 / 口径不一致）——直接命中
      2. 句内有「时间或双源信号」（两次、前后、改口…，或句内出现两个日期）
         且句内有**强差异词**（冲突、矛盾、不一致、对不上、改成…）
      3. 同信号 + **弱差异词**（不同 / 不一样）+ **主体词**（口径、说法、要求…）
      4. 句内是「原先…现在…」这种双段叙述，且句内有主体词

    取舍：**宁可多报也不漏报**。漏报的代价是两次口径被悄悄挑一个——那正是 G6
    存在的唯一理由；误报的代价只是作者改个措辞，报错会把命中的原句打出来。
    已知漏网：整句没有任何差异措辞的改口（如「后来改成走线下会签了」），
    这类纯语义判断正则做不了，只能靠人评审。
    """
    hits = []
    for raw in CLAUSE_SPLIT_RE.split(text):
        sent = raw.strip()
        if not sent:
            continue
        if LEGACY_CONFLICT_RE.search(sent):
            hits.append(sent)
            continue
        two_shot = CONFLICT_TWO_SHOT_RE.search(sent)
        signal = (CONFLICT_TEMPORAL_RE.search(sent) or two_shot
                  or len(CONFLICT_DATE_RE.findall(sent)) >= 2)
        if not signal:
            continue
        diverge = (CONFLICT_STRONG_RE.search(sent)
                   or (CONFLICT_WEAK_RE.search(sent)
                       and CONFLICT_SUBJECT_RE.search(sent)))
        if diverge or (two_shot and CONFLICT_SUBJECT_RE.search(sent)):
            hits.append(sent)
    return hits


# --------------------------------------------------------------------------- #
# 校验主逻辑
# --------------------------------------------------------------------------- #

def _check_g1(report: Report, base: str):
    texts = {}
    for name in SHAPING_FILES:
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            report.error("G1", "缺少 %s" % name)
            continue
        text = read_text(path)
        if text is None:
            report.error("G1", "%s 读取失败" % name)
        elif not text.strip():
            report.error("G1", "%s 为空" % name)
        else:
            texts[name] = text
    return texts


def _check_g2(report: Report, texts: dict):
    text = texts.get("01-problem.md")
    if text is None:
        return
    para = first_paragraph(text)
    if not para:
        report.error("G2", "01-problem.md 缺少产品定位首段（非标题/列表/表格的段落）")
        return
    n = count_sentences(para)
    if n == 0:
        report.error("G2", "01-problem.md 首段无句末标点，无法判定句数")
    elif n > 3:
        report.error("G2", "产品定位首段须 1–2 句（最多 3 句），当前 %d 句：%s…"
                     % (n, para[:40]))


def _check_g3(report: Report, texts: dict):
    text = texts.get("04-scope.md")
    if text is None:
        return
    found = {cat: False for cat in SCOPE_CATEGORIES}
    for heading, lines in split_sections(text):
        m = SCOPE_HEADING_RE.match(heading) if heading else None
        if not m:
            continue
        cat = m.group(1)
        found[cat] = True
        blocks = parse_blocks(lines)
        if not blocks:
            report.error("G3", "04-scope.md 的「%s」分类没有任何条目" % cat)
            continue
        if cat != "待确认":
            continue
        for anchor, body in blocks:
            combined = anchor + "\n" + "\n".join(body)
            if "拍板人" not in combined:
                report.error("G3", "「待确认」条目缺少拍板人：%s" % anchor.strip()[:50])
            if "影响面" not in combined:
                report.error("G3", "「待确认」条目缺少影响面：%s" % anchor.strip()[:50])
    for cat in SCOPE_CATEGORIES:
        if not found[cat]:
            report.error("G3", "04-scope.md 缺少「%s」分类标题" % cat)


def _check_g4(report: Report, texts: dict):
    text = texts.get("03-journey.md")
    if text is None:
        return
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "待定" in stripped:
            report.error("G4", "03-journey.md 出现「待定」：%s（要么写清楚，要么进 07-open-questions.md）"
                         % stripped[:60])
    has_branch = False
    for anchor, body in parse_blocks(lines):
        combined = anchor + "\n" + "\n".join(body)
        if not BRANCH_DEF_RE.search(combined):
            continue
        has_branch = True
        if not any(w in combined for w in BRANCH_VISIBLE_WORDS):
            report.error("G4", "分支未写明「用户看到什么」（%s）：%s"
                         % ("/".join(BRANCH_VISIBLE_WORDS), anchor.strip()[:60]))
    # 写成了分支、却没写成条目块（### 小标题、行首加粗…）：门禁看不见它，
    # 等于这个分支「用户看到什么」无人校验。静默跳过是回测里最大的一个漏。
    unparsed = [ln for ln in _lines_outside_blocks(lines) if BRANCH_DEF_RE.search(ln)]
    for line in unparsed:
        report.error("G4", "「分支：」没写成条目（门禁无法校验它是否写了「用户看到什么」）："
                           "%s（改用 `- ` 或 `1. ` 开头的顶层列表项）" % line.strip()[:60])
    if not has_branch and not unparsed:
        report.warn("W1", "03-journey.md 未发现任何「分支」条目（旅程无分支通常意味着没盘到位）")


def split_page_tokens(text: str):
    """把文本里的 kebab-case 词分成 (疑似页面 id, 形似但实为文档名/skill 名的排除项)。"""
    candidates, suspects = [], []
    for tok in PAGE_ID_RE.findall(text):
        if tok in NON_PAGE_TOKENS or JF_SKILL_RE.match(tok):
            if tok not in suspects:
                suspects.append(tok)
        elif tok not in candidates:
            candidates.append(tok)
    return candidates, suspects


def _page_field_value(combined: str, match) -> str:
    """取「影响页面:」字段的值（截到下一个 ｜/| 或行尾），报错时回显给作者看。"""
    rest = re.split(r"[｜|\n]", combined[match.end():], maxsplit=1)[0].strip()
    return rest[:40] or "（空）"


def entry_own_number(anchor: str):
    """取条目**自己的**编号，取不到返回 None。

    只认第一个 `｜` 之前的部分：条目正文里引用别的编号是正常的
    （如冲突条目的「阻塞: 同 OQ-01」），把它算进来会误报编号重复。
    """
    head = re.split(r"[｜|]", anchor, maxsplit=1)[0]
    found = OQ_NUM_RE.search(head)
    return found.group(0) if found else None


def _check_g5_g6(report: Report, texts: dict, page_ids=None):
    text07 = texts.get("07-open-questions.md")
    if text07 is None:
        return

    entries, conflicts = [], []
    for anchor, body in parse_blocks(text07.splitlines()):
        if not ENTRY_ANCHOR_RE.search(anchor):
            continue
        entries.append((anchor, body))
        if re.search(r"冲突[-：:]", anchor):
            conflicts.append((anchor, body))

    if not entries:
        report.warn("W2", "07-open-questions.md 未发现任何条目（OQ-编号 / 冲突条目）")

    # G5：每条可追溯到页面 id；给了 --manifest 则页面 id 必须真实存在。
    for anchor, body in entries:
        combined = anchor + "\n" + "\n".join(body)
        label = anchor.strip()[:60]
        candidates, suspects = split_page_tokens(combined)
        has_dr = bool(DR_REF_RE.search(combined))

        if suspects and not candidates:
            # 条目的页面证据只剩被排除的文档名/skill 名——正是「廉价满足」的写法
            report.warn("G5", "条目的页面 id 疑似写成了文档名/skill 名，已被排除、"
                              "不计入追溯依据：%s（%s）" % ("、".join(suspects), label))

        if page_ids is not None:
            unknown = [c for c in candidates if c not in page_ids]
            if unknown:
                report.error("G5", "条目引用的页面 id 不在 manifest.pages[] 中：%s（%s）"
                             % ("、".join(unknown), label))
            elif not candidates:
                # 给了 --manifest 就是要做页面级交叉校验。只靠 DR 编号追溯等于把这项
                # 关掉——旧实现只给 WARN，于是「影响页面: 见 DR 说明」和把页面名写成
                # 中文（专利提案详情）都全绿通过。中文名与「没写」在这里是同一种病：
                # 门禁取不到任何页面 id。分开给话术，作者才知道该改哪儿。
                field = PAGE_FIELD_RE.search(combined)
                if field:
                    report.error("G5", "条目的「影响页面」里没有可识别的页面 id"
                                       "（现写：%s）——须写 manifest.pages[] 里的页面 id"
                                       "（小写字母+数字+连字符）：%s"
                                 % (_page_field_value(combined, field), label))
                else:
                    report.error("G5", "条目未写「影响页面」字段，无法做页面交叉校验：%s"
                                 % label)
        elif not (candidates or has_dr):
            report.error("G5", "条目无法追溯到页面 id 或 MRD 的 DR 编号：%s" % label)

        if "拍板人" not in combined or "阻塞" not in combined:
            report.warn("W2", "条目缺「拍板人/阻塞」字段：%s" % anchor.strip()[:50])

    # G6：冲突单列在 07，不自行裁决
    for anchor, body in conflicts:
        quoted = [ln for ln in body if YUANHUA_RE.search(ln)]
        if len(quoted) < 2:
            report.error("G6", "冲突条目须并列 ≥2 条「原话」（当前 %d 条）：%s"
                         % (len(quoted), anchor.strip()[:50]))
        for ln in quoted:
            if "来源" not in ln:
                report.error("G6", "冲突原话缺少来源：%s" % ln.strip()[:60])
            elif not DATE_RE.search(ln):
                report.error("G6", "冲突原话缺少时间点（年-月-日）：%s" % ln.strip()[:60])

    for name in SHAPING_FILES[:-1]:  # 00–06：出现冲突字样必须对应 07 冲突条目
        text = texts.get(name)
        if not text:
            continue
        hits = find_conflict_markers(text)
        if hits and not conflicts:
            report.error("G6", "%s 出现疑似冲突口径（「%s」），但 07-open-questions.md "
                               "没有单列冲突条目" % (name, hits[0][:50]))


def _check_g7(report: Report, texts: dict):
    """G7：04-scope 的「待确认」与 07 的条目编号必须一一对应。

    两处是同一份清单的两个视图（scope 写影响面、07 写拍板人与阻塞），各自校验过
    却从不比对——回测注入：07 从 8 条砍到 1 条，门禁全绿，scope 里悬着的 7 条
    无人发现。要求 scope 每条待确认带 OQ 编号，再比两边编号集合。
    """
    text04 = texts.get("04-scope.md")
    text07 = texts.get("07-open-questions.md")
    if text04 is None or text07 is None:
        return

    scope_nums = []
    for heading, lines in split_sections(text04):
        if not heading:
            continue
        m = SCOPE_HEADING_RE.match(heading)
        if not m or m.group(1) != "待确认":
            continue
        for anchor, _body in parse_blocks(lines):
            num = entry_own_number(anchor)
            if not num:
                report.error("G7", "「待确认」条目未标 OQ 编号（须与 07-open-questions.md "
                                   "的编号一致）：%s" % anchor.strip()[:50])
                continue
            scope_nums.append(num)

    oq_nums = []
    for anchor, _body in parse_blocks(text07.splitlines()):
        if not ENTRY_ANCHOR_RE.search(anchor):
            continue
        num = entry_own_number(anchor)
        if num:
            oq_nums.append(num)

    for label, nums in (("04-scope.md 的「待确认」", scope_nums),
                        ("07-open-questions.md", oq_nums)):
        dupes = sorted({n for n in nums if nums.count(n) > 1})
        if dupes:
            report.error("G7", "%s 的 OQ 编号重复：%s" % (label, "、".join(dupes)))

    only_scope = sorted(set(scope_nums) - set(oq_nums))
    only_07 = sorted(set(oq_nums) - set(scope_nums))
    if only_scope:
        report.error("G7", "04-scope.md 的「待确认」有 %s，但 07-open-questions.md "
                           "没有对应条目" % "、".join(only_scope))
    if only_07:
        report.error("G7", "07-open-questions.md 的 %s 未登记到 04-scope.md 的「待确认」"
                     % "、".join(only_07))


def validate(base: str, page_ids=None) -> Report:
    """校验 shaping 目录，base 为 8 件套所在目录。

    page_ids 非 None 时（来源：--manifest），G5 会把条目引用的页面 id
    与 manifest.pages[].id 交叉校验，不存在的直接判 ERROR。
    """
    report = Report()
    texts = _check_g1(report, base)
    _check_g2(report, texts)
    _check_g3(report, texts)
    _check_g4(report, texts)
    _check_g5_g6(report, texts, page_ids)
    _check_g7(report, texts)
    if texts.get("00-intake.md") and "MRD" not in texts["00-intake.md"]:
        report.warn("W3", "00-intake.md 未提及上游 MRD（冷启动可忽略，移交 jf-prd 前建议补 jf-mrd）")
    return report


def load_page_ids(manifest_path: str):
    """读 manifest 的 pages[].id，返回集合；结构不合法时抛 ValueError。"""
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    if not isinstance(manifest, dict):
        raise ValueError("manifest 顶层必须是对象")
    pages = manifest.get("pages")
    if not isinstance(pages, list):
        raise ValueError("manifest 缺少 pages 数组")
    ids = {p["id"] for p in pages
           if isinstance(p, dict) and isinstance(p.get("id"), str)}
    if not ids:
        raise ValueError("manifest 的 pages[] 里没有任何有效 id")
    return ids


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def render_text(report: Report, base: str, manifest_path=None) -> str:
    lines = []
    lines.append("校验对象：%s" % base)
    if manifest_path:
        lines.append("G5 交叉校验：%s（条目引用的页面 id 必须存在于 manifest.pages[]）"
                     % manifest_path)
    lines.append("")
    if not report.issues:
        lines.append("✅ 全部通过，无问题。")
        return "\n".join(lines)
    if report.errors:
        lines.append("❌ 错误 %d 条（G1–G7 未通过，不放行到 jf-prd）：" % len(report.errors))
        lines.extend(str(i) for i in report.errors)
        lines.append("")
    if report.warnings:
        lines.append("⚠️  警告 %d 条：" % len(report.warnings))
        lines.extend(str(i) for i in report.warnings)
        lines.append("")
    if not report.errors:
        lines.append("✅ 门禁通过%s。" % ("；但有 %d 条警告" % len(report.warnings) if report.warnings else ""))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="校验 jf-interview shaping 8 件套门禁（G1–G7）")
    parser.add_argument("directory", nargs="?", help="shaping 目录路径（含 8 个 md 文件）")
    parser.add_argument("--manifest", metavar="PATH", default=None,
                        help="manifest.json 路径（jf-ia 产物）：G5 会交叉校验条目"
                             "引用的页面 id 是否真实存在")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="输出机读 JSON 报告")
    parser.add_argument("--self-test", action="store_true",
                        help="用内置合法/非法样例验证脚本本身")
    args = parser.parse_args(argv)

    if args.self_test:
        # 样例与断言在同目录 _selftest.py（#161 拆出）；判定依赖注入而非反向
        # import——本文件以 __main__ 运行时按名 import 会加载出第二份模块。
        import _selftest
        return _selftest.run(validate, BRANCH_VISIBLE_WORDS)
    if not args.directory:
        parser.print_help()
        return 2

    page_ids = None
    manifest_path = None
    if args.manifest:
        manifest_path = os.path.abspath(args.manifest)
        if not os.path.isfile(manifest_path):
            print("找不到 manifest：%s" % manifest_path, file=sys.stderr)
            return 2
        try:
            page_ids = load_page_ids(manifest_path)
        except (OSError, ValueError) as e:
            print("manifest 解析失败：%s" % e, file=sys.stderr)
            return 2

    base = os.path.abspath(args.directory)
    if not os.path.isdir(base):
        print("找不到 shaping 目录：%s" % base, file=sys.stderr)
        return 2

    report = validate(base, page_ids)

    if args.as_json:
        print(json.dumps({
            "directory": base,
            "manifest": manifest_path,
            "passed": len(report.errors) == 0,
            "errorCount": len(report.errors),
            "warningCount": len(report.warnings),
            "issues": [i.as_dict() for i in report.issues],
        }, ensure_ascii=False, indent=2))
    else:
        print(render_text(report, base, manifest_path))

    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
