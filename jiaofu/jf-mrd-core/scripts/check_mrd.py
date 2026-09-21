#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_mrd.py — jf-mrd-core 产物（MRD）校验门禁

校验一份 MRD 是否满足 jf-mrd-core 定义的门禁。契约全文见：
  products/jiaofu/jf-mrd-core/SKILL.md
    「MRD 头部 front-matter」（10 个必填字段）
    「9 个内容块」（PV/BRO/BEN/CP/UC/JF/BR/SM/DR）
  products/jiaofu/jf-mrd-core/references/rule-schema.md
    （BR 原始层条目 6 字段 + 来源的四种形态）

用法：
  python3 check_mrd.py <MRD文件> [--json]
  python3 check_mrd.py --self-test        # 用内置合法/非法样例验证脚本本身

查什么（逐条对应门禁原文）：

  F1  front-matter 存在且合法   `---` 包裹 + 符合 schema 形状（见下）
  F2  10 个必填字段齐           title/business_owner/version/status/updated/
                                requires/scope/coverage/reuse_assessment/changelog
  F3  字段值合法                version 形如 vX.Y；updated 是日期；标量字段非空
  F4  requires 非空             下游据此判断依赖就绪（SKILL.md 门禁原文）
  L1  changelog 非空
  K1  9 个内容块齐
  D1  DR 每条有拍板日期         「业务方拍板过的每个事项必须有一条决策记录」
  D2  DR 每条有来源
  R1  BR 每条 6 字段齐          规则ID/[原话]/[解读]/标签/来源/状态

**为什么不用 PyYAML**：本套件随 skill 发布的脚本一律零外部依赖（同 check_shaping /
check_design / validate_manifest）。front-matter 的 schema 是封闭的——10 个标量字段
+ 3 个一级列表字段——所以这里按这个形状自己解析；超出形状的写法（嵌套 map、
多行 `|` 块）判 F1，并说清改法。

退出码：
  0  通过（无 ERROR；WARN 仍算通过）
  1  未通过（存在 ERROR）
  2  用法错误 / 文件不存在 / 不可读
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

ERROR = "ERROR"
WARN = "WARN"

# ---------------------------------------------------------------- front-matter

# 必填字段（SKILL.md「MRD 头部 front-matter」表中所有 ✓）：(字段, 中文名)
REQUIRED_FM = [
    ("title", "文档标题"),
    ("business_owner", "业务方"),
    ("version", "版本号"),
    ("status", "文档状态"),
    ("updated", "最近更新日期"),
    ("requires", "上游输入文件清单"),
    ("scope", "范围"),
    ("coverage", "覆盖度"),
    ("reuse_assessment", "复用评估"),
    ("changelog", "版本沿革"),
]
# 标量字段（值必须非空字符串）——比 REQUIRED_FM 多一个可选的 related 之外的全集
LIST_FM = {"requires", "related", "changelog"}

VERSION_RE = re.compile(r"^v\d+(?:\.\d+)*$")
# 日期三态：ISO、斜杠、中文
DATE_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{4}/\d{1,2}/\d{1,2}"
    r"|\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?")
# 来源：rule-schema「来源追溯」的四种形态 + 显式字段名。
# 认「会议 2026-08-01 / 章程§3.2 / 竞品推断·竞品A / 用户直接输入」，
# 也认作者更常用的「来源：」「出处：」「纪要」——判据是有没有可追溯的出处标识，
# 不是措辞。表格式条目里来源在列值上，同样命中。
SOURCE_RE = re.compile(
    r"来源|出处|会议\s*\d{4}|纪要|章程|竞品推断|用户直接输入|§")

_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)[ \t]*:[ \t]*(.*)$")
_ITEM_RE = re.compile(r"^[ \t]+-[ \t]+(.*)$")
_FLOW_RE = re.compile(r"^\[(.*)\]$")


def _scalar(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v.strip()


def split_front_matter(text: str):
    """切出 front-matter 正文。返回 (yaml_text, error_message)。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, "文件未以 `---` 开头（MRD 头部元数据必须放 front-matter，不用正文 bullet 块）"
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), None
    return None, "front-matter 未闭合——第 1 行的 `---` 之后找不到第二个 `---`"


def parse_front_matter(block: str):
    """按封闭 schema 解析：一级 `key: value` + 缩进 `- item`，或 `key: [a, b]`。

    返回 (data, error_message)。data 的 list 字段一定是 list，标量字段一定是 str。
    """
    data: dict = {}
    current = None
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        item = _ITEM_RE.match(raw)
        if item:
            if current is None or not isinstance(data.get(current), list):
                return None, ("列表项 `- %s` 没有归属的列表字段——"
                              "列表字段要写成 `字段名:` 换行后缩进 `- 值`"
                              % item.group(1).strip()[:40])
            data[current].append(_scalar(item.group(1)))
            continue
        if raw[:1] in (" ", "\t"):
            return None, ("不支持嵌套结构（`%s`）——front-matter 只允许"
                          "「一级标量字段 + 一级列表字段」"
                          % raw.strip()[:40])
        m = _KV_RE.match(raw)
        if not m:
            return None, "无法解析的行：`%s`（只支持 `字段名: 值`）" % raw.strip()[:60]
        key, value = m.group(1), m.group(2).strip()
        if key in data:
            return None, "字段 `%s` 重复" % key
        if value == "":
            data[key] = []
        else:
            flow = _FLOW_RE.match(value)
            if flow:
                inner = flow.group(1).strip()
                data[key] = [_scalar(x) for x in inner.split(",")] if inner else []
            else:
                data[key] = _scalar(value)
        current = key
    return data, None


# ---------------------------------------------------------------- 9 个内容块

# (块码, 中文名, 标题里的块码，正文里的 ID 形态或 None)
# 标题命中「块码」或正文出现「ID 形态」都算这一块在——UC/JF/BR/SM 是嵌套章节
# （UC 嵌 CP、JF 嵌 UC、BR/SM 嵌 JF），标题不一定带块码，但编号必须全局连续。
BLOCKS = [
    ("PV", "产品愿景", "PV", None),
    ("BRO", "业务角色", "BRO", None),
    ("BEN", "业务实体", "BEN", None),
    ("CP", "核心流程", "CP", r"CP-\d+"),
    ("UC", "业务用例", "UC", r"UC-\d+"),
    ("JF", "用户旅程", "JF", r"JF-\d+"),
    ("BR", "业务规则", "BR", r"BR-\d+"),
    ("SM", "状态机", "SM", r"SM-\d+"),
    ("DR", "决策记录", "DR", None),
]

HEADING_RE = re.compile(r"^(#{1,6})[ \t]*(.*)$")
TABLE_ROW_RE = re.compile(r"^[ \t]*\|")


def _code_re(code: str) -> re.Pattern:
    """块码整词匹配——不让 `BR` 命中 `BRO`、`SM` 命中 `SMxx`。"""
    return re.compile(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(code))


def _headings(text: str):
    """[(行号, 级别, 标题文本)]。"""
    out = []
    for i, line in enumerate(text.splitlines()):
        m = HEADING_RE.match(line)
        if m:
            out.append((i, len(m.group(1)), m.group(2)))
    return out


def _section(text: str, predicate):
    """取标题满足 predicate 的小节正文（到下一条同级或更高级标题为止）。"""
    lines = text.splitlines()
    for i, level, title in _headings(text):
        if predicate(title):
            body = []
            for j in range(i + 1, len(lines)):
                h = HEADING_RE.match(lines[j])
                if h and len(h.group(1)) <= level:
                    break
                body.append(lines[j])
            return "\n".join(body)
    return None


# ---------------------------------------------------------------- 条目切片

# 条目锚：行首（可带列表符/加粗标记/表格竖线）的块 ID。
# **必须锚在行首**——「追溯：BR-07」「（BR-07）」是正文引用不是条目，
# 若不锚定，一处交叉引用就会被当成一条只有半截内容的规则。
_ANCHOR_TPL = r"^[ \t]*(?:[-*+][ \t]+)?(?:\*\*[ \t]*)?\|?[ \t]*(%s)"
DR_ANCHOR_RE = re.compile(_ANCHOR_TPL % r"D-\d+")
BR_ANCHOR_RE = re.compile(_ANCHOR_TPL % r"BR-\d+")

# 条目正文的行数上限：条目到下一个锚点/下一条标题为止，
# 加这个兜底是防止「文档末尾最后一个条目」把后面所有内容都吞进来。
MAX_ENTRY_LINES = 60


def _entries(text: str, anchor_re: re.Pattern):
    """产出 [(条目ID, 条目正文)]。

    正文止于三者先到者：下一个锚点 / 下一条标题 / MAX_ENTRY_LINES 行。
    标题这条边界是必需的——文档最后一节条目后面若跟着「信息来源清单」这类
    标题，正文里的「来源」二字会冒充字段名把缺字段的条目蒙混过关。
    """
    lines = text.splitlines()
    heads = [i for i, _, _ in _headings(text)]
    anchors = [i for i, l in enumerate(lines) if anchor_re.match(l)]
    anchor_set = set(anchors)
    out = []
    for n, i in enumerate(anchors):
        end = len(lines)
        if n + 1 < len(anchors):
            end = min(end, anchors[n + 1])
        nxt = next((h for h in heads if h > i), None)
        if nxt is not None:
            end = min(end, nxt)
        end = min(end, i + MAX_ENTRY_LINES)
        body = "\n".join(lines[i:end])
        # 表格式条目：字段名（标签/状态/来源…）往往只在表头行上，
        # 逐行校验会误判缺失——把紧邻上方的表头并进切片。
        if TABLE_ROW_RE.match(lines[i]):
            j = i - 1
            head = []
            while j >= 0 and TABLE_ROW_RE.match(lines[j]) and j not in anchor_set:
                head.append(lines[j])
                j -= 1
            body = "\n".join(reversed(head)) + "\n" + body
        out.append((anchor_re.match(lines[i]).group(1), body))
    return out


# ---------------------------------------------------------------- 报告

class Issue:
    def __init__(self, level: str, code: str, message: str):
        self.level = level
        self.code = code
        self.message = message

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}


class Report:
    def __init__(self):
        self.issues: list = []

    def error(self, code: str, message: str):
        self.issues.append(Issue(ERROR, code, message))

    def warn(self, code: str, message: str):
        self.issues.append(Issue(WARN, code, message))

    @property
    def errors(self):
        return [i for i in self.issues if i.level == ERROR]

    @property
    def warnings(self):
        return [i for i in self.issues if i.level == WARN]


# ---------------------------------------------------------------- 校验主体

BR_FIELDS = [
    ("[原话]", re.compile(r"\[原话\]|原话\s*[:：]")),
    ("[解读]", re.compile(r"\[解读\]|解读\s*[:：]")),
    ("标签", re.compile(r"标签\s*[:：=|]|\|[^|\n]*标签[^|\n]*\||(?<=\s)#\S")),
    ("来源", SOURCE_RE),
    ("状态", re.compile(r"状态\s*[:：=|]|\|[^|\n]*状态[^|\n]*\|")),
]


def _check_front_matter(text: str, report: Report) -> dict:
    block, err = split_front_matter(text)
    if err:
        report.error("F1", err)
        return {}
    data, err = parse_front_matter(block)
    if err:
        report.error("F1", "front-matter 不是合法的 YAML 子集：%s" % err)
        return {}

    missing = [(f, cn) for f, cn in REQUIRED_FM if f not in data]
    if missing:
        report.error("F2", "front-matter 缺必填字段：%s"
                     % "、".join("%s（%s）" % (f, cn) for f, cn in missing))

    for field, cn in REQUIRED_FM:
        if field not in data:
            continue
        value = data[field]
        if field in LIST_FM:
            if not isinstance(value, list):
                report.error("F3", "字段 `%s`（%s）应是列表——写成 `%s:` 换行后缩进 `- 值`"
                             % (field, cn, field))
            continue
        if not isinstance(value, str) or not value.strip():
            report.error("F3", "字段 `%s`（%s）为空" % (field, cn))

    version = data.get("version")
    if isinstance(version, str) and version and not VERSION_RE.match(version):
        report.error("F3", "`version` 应为 vX.Y 形式，实际是 `%s`" % version)
    updated = data.get("updated")
    if isinstance(updated, str) and updated and not DATE_RE.search(updated):
        report.error("F3", "`updated` 不是日期，实际是 `%s`" % updated)

    requires = data.get("requires")
    if isinstance(requires, list):
        if not requires:
            report.error("F4", "`requires` 为空——下游据此判断依赖就绪，必须列出上游输入清单")
        elif any(not str(x).strip() for x in requires):
            report.error("F4", "`requires` 有空条目")

    changelog = data.get("changelog")
    if isinstance(changelog, list):
        if not changelog:
            report.error("L1", "`changelog` 为空——版本沿革随每版更新")
        else:
            for entry in changelog:
                if not re.search(r"v\d", str(entry)):
                    report.warn("W1", "`changelog` 条目无版本号：`%s`" % str(entry)[:40])
                    break
            if isinstance(version, str) and version and \
                    not any(version in str(e) for e in changelog):
                report.warn("W3", "`changelog` 里找不到当前 `version`（%s）——"
                                  "版本沿革与版本号可能没同步" % version)
    return data


def _check_blocks(text: str, report: Report):
    heads = [t for _, _, t in _headings(text)]
    missing = []
    for code, cn, head_code, id_re in BLOCKS:
        cre = _code_re(head_code)
        if any(cre.search(t) for t in heads):
            continue
        if code == "DR" and any("决策记录" in t for t in heads):
            continue
        if id_re and re.search(id_re, text):
            continue
        missing.append("%s（%s）" % (code, cn))
    if missing:
        report.error("K1", "MRD 缺内容块：%s——9 块齐了才是完整 MRD"
                     % "、".join(missing))


def _without_source_lines(body: str) -> str:
    """摘掉「来源 / 出处」那一行，再去找日期。

    D1 问的是「这条决策**哪天拍的板**」。「来源：会议 2026-08-01」里的日期是
    **来源的**日期，不是拍板日期——不摘掉的话，一个只有来源、没有拍板日期的
    条目会被那个日期蒙混过关，D1 就恒真了。

    带日期标签的行（`拍板日期：…`）不摘——它本来就是 D1 要找的东西。
    表格式条目里来源在列上，但那一行长得像 `| 取100 | 2026-08-01 | 会议 |`，
    不含「来源」二字，天然不会被摘掉。
    """
    keep = []
    for line in body.splitlines():
        if re.search(r"来源|出处", line) and not re.search(r"日期\s*[:：=|]", line):
            continue
        keep.append(line)
    return "\n".join(keep)


def _check_dr(text: str, report: Report):
    section = _section(text, lambda t: _code_re("DR").search(t) or "决策记录" in t)
    if section is None:
        return  # K1 已经报过缺块，这里不再重复刷屏
    for did, body in _entries(section, DR_ANCHOR_RE):
        if not DATE_RE.search(_without_source_lines(body)):
            report.error("D1", "%s 缺拍板日期——决策记录必须含日期" % did)
        if not SOURCE_RE.search(body):
            report.error("D2", "%s 缺来源——决策记录必须可追溯" % did)


def _check_br(text: str, report: Report):
    for bid, body in _entries(text, BR_ANCHOR_RE):
        missing = [name for name, rx in BR_FIELDS if not rx.search(body)]
        if missing:
            report.error("R1", "%s 缺字段：%s——原始层条目 6 字段（规则ID/[原话]/"
                               "[解读]/标签/来源/状态）必须齐" % (bid, "、".join(missing)))


def check_mrd(text: str) -> Report:
    report = Report()
    _check_front_matter(text, report)
    _check_blocks(text, report)
    _check_dr(text, report)
    _check_br(text, report)
    return report


def render_text(report: Report, path: str) -> str:
    lines = ["检查：%s" % path, ""]
    if not report.issues:
        lines.append("✅ 通过：front-matter 合法、requires 非空、9 个内容块齐、"
                     "DR 每条有日期与来源、BR 每条 6 字段齐")
        return "\n".join(lines)
    for issue in report.issues:
        lines.append("[%s] %-3s %s" % (issue.level, issue.code, issue.message))
    lines.append("")
    lines.append("结果：%d 个 ERROR，%d 个 WARN"
                 % (len(report.errors), len(report.warnings)))
    return "\n".join(lines)


# ---------------------------------------------------------------- self-test

_VALID = """---
title: 积分-MRD
business_owner: 运营部 · 积分运营岗（当前负责人：张三）
version: v0.1
status: 待评审
updated: 2026-08-01
requires:
  - 会议纪要/2026-08-01-积分-纪要.md
scope: 需求清单序号 3（运营 > 积分）——只做基础积分，不含兑换商城
coverage: ✅ 深度覆盖 积分获取与扣减；⚠️ 待提供 兑换规则
reuse_assessment: 与既有会员系统共用 BRO，无冲突
related:
  - 会员-MRD
changelog:
  - v0.1（2026-08-01）：首次成稿
---

# 积分-MRD

## 1. PV 产品愿景

让用户攒得住分。指标：30 天活跃 +15%；反指标：投诉率 ≤1%。

## 2. BRO 业务角色

- 积分运营岗：配置规则
- 会员：攒分与用分

## 3. BEN 业务实体

积分账户、积分流水。层级：积分账户是聚合根，积分流水是子。

## 4. CP 核心流程

### 4.1 CP-01 积分获取

#### 4.1.1 UC-01 会员完成任务得分

会员（BRO）对积分账户（BEN）加分。

##### 4.1.1.1 JF-01 完成任务得分旅程（CP-01 › UC-01 ｜ 会员）

- 进入任务页 → 完成任务 → 系统加分

**业务规则**

- **BR-01**
  - [原话] "一天最多加 100 分"
  - [解读] "同一会员单日累计加分上限 100"
  - 标签：[金额][边界] #积分 #P0
  - 来源：会议 2026-08-01
  - 状态：已确认

**业务状态切换**

##### 4.1.1.2 SM-01 积分账户状态机（CP-01 › UC-01 › JF-01）

- 正常 → 冻结 → 正常

## 5. 需求级全局规则

跨 UC 的边界规则：保密类 BR-02 挂需求层。

## 6. DR 决策记录

- **D-01** 积分上限取 100 还是 200
  - 结论：取 100
  - 拍板日期：2026-08-01
  - 来源：会议 2026-08-01

## 7. 术语表

积分：可累计的虚拟权益。

## 8. 信息来源清单

- 会议纪要/2026-08-01-积分-纪要.md

## 附 A. 待确认清单

- A.1 D-01 ✅ 已拍板
"""


def _mutate(old: str, new: str) -> str:
    assert old in _VALID, "self-test 注入锚点未命中：%r" % old[:60]
    return _VALID.replace(old, new, 1)


def _codes(report: Report):
    return [i.code for i in report.errors], [i.code for i in report.warnings]


def self_test() -> int:
    cases = []

    # 合法样例必须过
    cases.append(("合法 MRD 通过", _VALID, [], []))

    # front-matter
    cases.append(("无 front-matter",
                  _VALID.split("---\n", 2)[2], ["F1"], None))
    cases.append(("front-matter 未闭合",
                  _VALID.replace("---\n\n# 积分-MRD", "\n# 积分-MRD", 1), ["F1"], None))
    cases.append(("缺必填字段（reuse_assessment）",
                  _mutate("reuse_assessment: 与既有会员系统共用 BRO，无冲突\n", ""),
                  ["F2"], None))
    cases.append(("requires 为空", _mutate(
        "requires:\n  - 会议纪要/2026-08-01-积分-纪要.md\n", "requires: []\n"),
        ["F4"], None))
    cases.append(("version 格式非法",
                  _mutate("version: v0.1", "version: 0.1"), ["F3"], None))
    cases.append(("updated 不是日期",
                  _mutate("updated: 2026-08-01", "updated: 前天"), ["F3"], None))
    cases.append(("嵌套结构不支持",
                  _mutate("scope: 需求清单序号 3", "scope:\n  a: 1\nscope2: 需求清单序号 3"),
                  ["F1"], None))
    cases.append(("changelog 为空",
                  _mutate("changelog:\n  - v0.1（2026-08-01）：首次成稿\n", "changelog: []\n"),
                  ["L1"], None))

    # 9 个内容块
    cases.append(("缺 SM 块",
                  _mutate("##### 4.1.1.2 SM-01 积分账户状态机（CP-01 › UC-01 › JF-01）\n\n"
                          "- 正常 → 冻结 → 正常\n\n", ""), ["K1"], None))
    cases.append(("缺 DR 块（连同 D-01 一起摘掉，只报 K1 不刷屏 D1/D2）",
                  _mutate("## 6. DR 决策记录\n\n- **D-01** 积分上限取 100 还是 200\n"
                          "  - 结论：取 100\n  - 拍板日期：2026-08-01\n"
                          "  - 来源：会议 2026-08-01\n\n", ""), ["K1"], None))

    # DR 每条有日期与来源
    cases.append(("DR 缺日期（只剩来源，来源里的日期不算拍板日期）",
                  _mutate("  - 结论：取 100\n  - 拍板日期：2026-08-01\n",
                          "  - 结论：取 100\n"), ["D1"], None))
    cases.append(("DR 缺来源",
                  _mutate("  - 拍板日期：2026-08-01\n  - 来源：会议 2026-08-01\n",
                          "  - 拍板日期：2026-08-01\n"), ["D2"], None))
    cases.append(("DR 两条，只查得出缺日期的那条", _mutate(
        "- **D-01** 积分上限取 100 还是 200\n"
        "  - 结论：取 100\n"
        "  - 拍板日期：2026-08-01\n"
        "  - 来源：会议 2026-08-01\n",
        "- **D-01** 积分上限取 100 还是 200\n"
        "  - 结论：取 100\n"
        "  - 来源：会议 2026-08-01\n"
        "\n- **D-02** 冻结态能否消费\n"
        "  - 结论：不能\n"
        "  - 拍板日期：2026-08-02\n"
        "  - 来源：会议 2026-08-02\n"), ["D1"], None))

    # BR 六字段
    cases.append(("BR 缺 [解读]",
                  _mutate('  - [解读] "同一会员单日累计加分上限 100"\n', ""),
                  ["R1"], None))
    cases.append(("BR 缺 标签",
                  _mutate("  - 标签：[金额][边界] #积分 #P0\n", ""), ["R1"], None))
    cases.append(("BR 缺 状态",
                  _mutate("  - 状态：已确认\n", ""), ["R1"], None))
    cases.append(("BR 缺 来源",
                  _mutate("  - 来源：会议 2026-08-01\n", ""), ["R1"], None))

    # 正文引用不是条目——锚点必须锚在行首
    cases.append(("行内引用 `追溯：BR-07` 不被当成条目",
                  _mutate("积分：可累计的虚拟权益。",
                          "积分：可累计的虚拟权益（追溯：BR-01）。"), [], None))

    # 表格式条目：字段名在表头行上
    cases.append(("表格式 BR/DR 条目也认得出字段", _mutate(
        "- **BR-01**\n"
        '  - [原话] "一天最多加 100 分"\n'
        '  - [解读] "同一会员单日累计加分上限 100"\n'
        "  - 标签：[金额][边界] #积分 #P0\n"
        "  - 来源：会议 2026-08-01\n"
        "  - 状态：已确认\n",
        "| 规则ID | [原话] | [解读] | 标签 | 来源 | 状态 |\n"
        "|---|---|---|---|---|---|\n"
        "| BR-01 | 一天最多加 100 分 | 单日累计上限 100 | [金额][边界] | "
        "会议 2026-08-01 | 已确认 |\n"), [], None))

    # 条目切片必须以标题为界：D-01 缺日期缺来源，而紧随其后的子标题里
    # 恰好有「拍板日期」「来源」——若切片吞到下一节，这两个 ERROR 就消失了。
    cases.append(("末节条目切片被下一条标题截断（后文的日期/来源捡不过来）", _mutate(
        "  - 结论：取 100\n  - 拍板日期：2026-08-01\n  - 来源：会议 2026-08-01\n"
        "\n## 7. 术语表",
        "  - 结论：取 100\n\n### 6.1 决策台账\n\n"
        "- 拍板日期：2026-08-02\n- 来源：会议 2026-08-02\n\n## 7. 术语表"),
        ["D1", "D2"], None))

    failures = []
    for name, text, expect_errors, expect_warns in cases:
        got_e, got_w = _codes(check_mrd(text))
        ok = got_e == expect_errors
        if expect_warns is not None:
            ok = ok and got_w == expect_warns
        if not ok:
            failures.append("  ✗ %s\n      期望 ERROR %s，实得 %s\n"
                            "      期望 WARN  %s，实得 %s"
                            % (name, expect_errors, got_e, expect_warns, got_w))
    if failures:
        print("self-test 失败 %d/%d：" % (len(failures), len(cases)))
        print("\n".join(failures))
        return 1
    print("self-test 通过：%d 个用例（1 合法 + %d 非法/边界）"
          % (len(cases), len(cases) - 1))
    return 0


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="校验 jf-mrd-core 产物（MRD）：front-matter / 9 个内容块 / "
                    "DR 日期来源 / BR 六字段")
    parser.add_argument("mrd", nargs="?", help="MRD 文件路径")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="输出机读 JSON 报告")
    parser.add_argument("--self-test", action="store_true",
                        help="用内置合法/非法样例验证脚本本身")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.mrd:
        parser.print_help()
        return 2

    path = os.path.abspath(args.mrd)
    if not os.path.isfile(path):
        print("找不到 MRD：%s" % path, file=sys.stderr)
        return 2
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print("MRD 读取失败：%s" % e, file=sys.stderr)
        return 2

    report = check_mrd(text)
    if args.as_json:
        print(json.dumps({
            "mrd": path,
            "passed": len(report.errors) == 0,
            "errorCount": len(report.errors),
            "warningCount": len(report.warnings),
            "issues": [i.as_dict() for i in report.issues],
        }, ensure_ascii=False, indent=2))
    else:
        print(render_text(report, path))
    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
