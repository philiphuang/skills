#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_manifest.py — jf-* 契约层校验门禁

校验 manifest.json 是否满足 jf-contract 定义的不变条件（I1–I12）以及
文件/HTML 级一致性（F1–F4）。契约全文见：
  products/jiaofu/jf-contract/references/manifest-schema.md

用法：
  python3 validate_manifest.py <manifest.json> [--root DIR] [--strict] [--json]
  python3 validate_manifest.py --self-test        # 用内置样例验证脚本本身

退出码：
  0  通过（无 ERROR；WARN 仍算通过，除非 --strict）
  1  未通过（存在 ERROR；--strict 下存在 WARN 也算未通过）
  2  用法错误 / manifest 无法解析
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

SCHEMA_VERSION = 1
VALID_NAV = ("standalone", "sub-flow")
VALID_FRAME = ("route", "modal")
VALID_DEVICE = ("desktop", "mobile")
VALID_KIND = ("list", "detail", "form", "dashboard", "confirm", "external")
VALID_REL_TYPE = ("route", "modal", "tab", "external")
# 标注气泡的三态。契约源：products/jiaofu/jf-contract/references/manifest-schema.md#annotations
# 渲染器（jf-uxprompt/scripts/render_manifest.py）另有一份同名常量——
# 两个脚本分属不同 skill、以子进程方式各自运行，没法共享；
# 一致性由 tests/unit/scripts/test_render_manifest.py 的用例盯着。
VALID_ANNOTATION_STATUS = ("active", "resolved", "rejected")
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

ERROR = "ERROR"
WARN = "WARN"


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
# HTML 解析（只用标准库正则，避免依赖 bs4）
# --------------------------------------------------------------------------- #

ANCHOR_RE = re.compile(r"<a\b[^>]*>", re.IGNORECASE)
HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
NAV_RE = re.compile(r"""data-nav\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def parse_anchors(html: str):
    """返回 [(href, data_nav), ...]"""
    out = []
    for tag in ANCHOR_RE.findall(html or ""):
        href = HREF_RE.search(tag)
        nav = NAV_RE.search(tag)
        if href or nav:
            out.append((href.group(1) if href else None,
                        nav.group(1) if nav else None))
    return out


def basename_no_ext(path: str) -> str:
    base = os.path.basename(path or "")
    return os.path.splitext(base)[0]


def nav_target(href: str) -> str:
    """取 href 的「跳转目标文件名」，先剥 query 与 fragment。

    演示档的控制台用 `./score-form.html?state=warning` 驱动目标页切到某个状态
    （见 jf-uxprompt 的 console.html）——那是**同一个跳转目标**，不是另一个页面。
    直接取 basename 会把 `?state=warning` 当成文件名的一部分，让 F3 与链接可达性
    检查双双误判成「找不到链接 / 链接不可达」。
    """
    return os.path.basename(href.split("?", 1)[0].split("#", 1)[0])


# FR/AC/BR/SM/UC 编号：PM 内部语言，不该出现在给客户看的场景名里（I12）。
# 用 `(?<![A-Za-z])` 而不是 `\b` 划左界：Python 的 `\b` 把中日韩字符也算「词字符」，
# 「基础积分达上限AC-05-3」这种编号**紧跟中文**的写法在 `\b` 下会漏网——
# 而这个门禁宁可多报（改个标题的事）也不能漏（编号漏到客户面前才知道）。
CODE_REF_RE = re.compile(r"(?<![A-Za-z])(?:FR|AC|BR|SM|UC)-\d")


# 侧边导航整块：结构性链接不属于 relations 校验范围。
# 用非贪婪匹配剔除**全部** <nav> 块——只剔第一个的话，一旦加移动端抽屉导航
# （第二组 nav），抽屉里的链接会被误判成「relations 未声明的跳转」。
# <nav> 按 HTML 语义即导航地标，整体豁免；正文里的跳转链接仍逐条校验。
NAV_BLOCK_RE = re.compile(r"<nav\b[^>]*>.*?</nav\s*>", re.IGNORECASE | re.DOTALL)


def strip_nav_block(page_html: str) -> str:
    """去掉全部 <nav> 块——结构性导航链接不属于 relations 校验范围。"""
    return NAV_BLOCK_RE.sub("", page_html or "")


# 标注协议允许的两种稳定 selector 形式
ANN_ID_RE = re.compile(r"^#([A-Za-z0-9_-]+)$")
ANN_ATTR_RE = re.compile(
    r"^\[\s*data-annotation-anchor\s*=\s*[\"']?([A-Za-z0-9_-]+)[\"']?\s*\]$")


def annotation_target_in_html(target: str, page_html):
    """判断标注 target 能否在页面 HTML 中定位到元素。

    只认 #id 与 [data-annotation-anchor=值] 两种形式（对齐标注协议）；
    其余形式（nth-child / 显示文案 / 复合 selector）返回 None 表示不可解析。
    """
    m = ANN_ID_RE.match(target)
    if m:
        v = m.group(1)
        return ('id="%s"' % v) in page_html or ("id='%s'" % v) in page_html
    m = ANN_ATTR_RE.match(target)
    if m:
        v = m.group(1)
        return ('data-annotation-anchor="%s"' % v) in page_html \
            or ("data-annotation-anchor='%s'" % v) in page_html
    return None


# --------------------------------------------------------------------------- #
# 校验主逻辑
# --------------------------------------------------------------------------- #

def _check_id(report: Report, code: str, value, label: str, seen: dict):
    if not isinstance(value, str) or not value:
        report.error(code, "%s 的 id 缺失或不是字符串：%r" % (label, value))
        return
    if not ID_RE.match(value):
        report.error(code, "%s id 非法（只允许小写字母/数字/连字符）：%r" % (label, value))
    if value in seen:
        report.error(code, "%s id 重复：%r（同时被 %s 使用）" % (label, value, seen[value]))
    else:
        seen[value] = label


def validate(manifest: dict, root: str = ".", strict: bool = False) -> Report:
    """校验 manifest 字典，root 为 file 字段的相对根目录。"""
    report = Report()

    if not isinstance(manifest, dict):
        report.error("S0", "manifest 顶层必须是对象")
        return report

    # ---------- S0 顶层结构 ----------
    if "schemaVersion" not in manifest:
        report.warn("S0", "缺少 schemaVersion，按 %d 处理" % SCHEMA_VERSION)
    elif manifest["schemaVersion"] != SCHEMA_VERSION:
        report.warn("S0", "schemaVersion=%r 与当前契约 %d 不一致，需迁移"
                    % (manifest["schemaVersion"], SCHEMA_VERSION))

    if not isinstance(manifest.get("product"), dict):
        report.error("S0", "缺少 product 对象")
    if not isinstance(manifest.get("modules"), list) or not manifest["modules"]:
        report.error("S0", "modules 必须是非空数组")
        modules = []
    else:
        modules = manifest["modules"]
    if not isinstance(manifest.get("pages"), list) or not manifest["pages"]:
        report.error("S0", "pages 必须是非空数组")
        pages = []
    else:
        pages = manifest["pages"]
    relations = manifest.get("relations") or []
    components = manifest.get("components") or []
    if not isinstance(relations, list):
        report.error("S0", "relations 必须是数组")
        relations = []
    if not isinstance(components, list):
        report.error("S0", "components 必须是数组")
        components = []

    # ---------- modules：I4 / I6 ----------
    module_ids = {}
    for i, m in enumerate(modules):
        label = "modules[%d]" % i
        if not isinstance(m, dict):
            report.error("S0", "%s 必须是对象" % label)
            continue
        _check_id(report, "I4", m.get("id"), label, module_ids)
        if not m.get("title"):
            report.error("S0", "%s 缺少 title" % label)

    # ---------- pages ----------
    page_ids = {}
    page_by_id = {}
    for i, p in enumerate(pages):
        label = "pages[%d]" % i
        if not isinstance(p, dict):
            report.error("S0", "%s 必须是对象" % label)
            continue
        pid = p.get("id")
        _check_id(report, "I4", pid, label, page_ids)
        if not isinstance(pid, str):
            continue
        page_by_id[pid] = p

        if not p.get("title"):
            report.error("S0", "页面 %s 缺少 title" % pid)
        if not p.get("obj"):
            report.warn("S0", "页面 %s 缺少 obj（主管理对象）" % pid)

        # I1：id 必须等于 file 的 basename
        pfile = p.get("file")
        if not pfile:
            report.error("I1", "页面 %s 缺少 file" % pid)
        elif basename_no_ext(pfile) != pid:
            report.error("I1", "页面 %s 的 file basename 为 %r，与 id 不一致"
                         % (pid, basename_no_ext(pfile)))

        # nav / frame 枚举
        nav = p.get("nav")
        if nav not in VALID_NAV:
            report.error("S0", "页面 %s 的 nav=%r 非法（应为 %s）"
                         % (pid, nav, "/".join(VALID_NAV)))
        frame = p.get("frame")
        if frame not in VALID_FRAME:
            report.error("S0", "页面 %s 的 frame=%r 非法（应为 %s）"
                         % (pid, frame, "/".join(VALID_FRAME)))
        kind = p.get("kind")
        if kind not in VALID_KIND:
            report.error("S0", "页面 %s 的 kind=%r 非法（应为 %s）"
                         % (pid, kind, "/".join(VALID_KIND)))

        # I3：sub-flow 必须有 hostPageId
        host = p.get("hostPageId")
        if nav == "sub-flow" and not host:
            report.error("I3", "页面 %s 是 sub-flow 但缺少 hostPageId" % pid)

        # I5：device / viewport
        if p.get("device") not in VALID_DEVICE:
            report.error("I5", "页面 %s 的 device=%r 非法（应为 %s）"
                         % (pid, p.get("device"), "/".join(VALID_DEVICE)))
        vp = p.get("viewport")
        if not isinstance(vp, dict):
            report.error("I5", "页面 %s 缺少 viewport 对象" % pid)
        else:
            w, h = vp.get("width"), vp.get("height")
            if not (isinstance(w, int) and not isinstance(w, bool) and w > 0):
                report.error("I5", "页面 %s 的 viewport.width 必须为正整数：%r" % (pid, w))
            if not (isinstance(h, int) and not isinstance(h, bool) and h > 0):
                report.error("I5", "页面 %s 的 viewport.height 必须为正整数：%r" % (pid, h))

        # I7：D 必须写业务替代动作
        crud = p.get("crud")
        if not crud:
            report.error("S0", "页面 %s 缺少 crud" % pid)
        elif isinstance(crud, str) and "D" in crud.upper():
            note = (p.get("crudNote") or "").strip()
            if not note:
                report.error("I7", "页面 %s 的 crud 含 D，必须写 crudNote（业务替代动作，如停用/退回/覆盖导入）" % pid)

        # I8：states 非空且含 default
        states = p.get("states")
        if not isinstance(states, list) or not states:
            report.error("I8", "页面 %s 的 states 不能为空" % pid)
        elif "default" not in states:
            report.error("I8", "页面 %s 的 states 必须包含 default：%r" % (pid, states))

        # moduleId 引用
        mid = p.get("moduleId")
        if not mid:
            report.error("S0", "页面 %s 缺少 moduleId" % pid)

    # I6：每个 module 至少被一个 page 引用
    referenced_modules = {p.get("moduleId") for p in pages if isinstance(p, dict)}
    for m in modules:
        if isinstance(m, dict) and m.get("id") and m["id"] not in referenced_modules:
            report.error("I6", "module %s 没有被任何页面引用" % m["id"])

    # page.moduleId 必须存在
    for p in pages:
        if not isinstance(p, dict):
            continue
        mid = p.get("moduleId")
        if mid and module_ids and mid not in module_ids:
            report.error("S0", "页面 %s 的 moduleId=%r 不存在" % (p.get("id"), mid))

    # I3 补充：宿主页必须是 standalone
    for p in pages:
        if not isinstance(p, dict):
            continue
        host = p.get("hostPageId")
        if not host:
            continue
        hp = page_by_id.get(host)
        if hp is None:
            report.error("I3", "页面 %s 的 hostPageId=%r 指向不存在的页面" % (p.get("id"), host))
        elif hp.get("nav") != "standalone":
            report.error("I3", "页面 %s 的宿主 %s 不是 standalone（当前 %r）"
                         % (p.get("id"), host, hp.get("nav")))

    # ---------- relations：I2 / I4 / I10 ----------
    rel_ids = {}
    for i, r in enumerate(relations):
        label = "relations[%d]" % i
        if not isinstance(r, dict):
            report.error("S0", "%s 必须是对象" % label)
            continue
        _check_id(report, "I4", r.get("id"), label, rel_ids)
        src, dst = r.get("from"), r.get("to")
        # I2
        if src not in page_by_id:
            report.error("I2", "关系 %s 的 from=%r 不存在" % (r.get("id"), src))
        if dst not in page_by_id:
            report.error("I2", "关系 %s 的 to=%r 不存在" % (r.get("id"), dst))
        rtype = r.get("type")
        if rtype not in VALID_REL_TYPE:
            report.error("S0", "关系 %s 的 type=%r 非法（应为 %s）"
                         % (r.get("id"), rtype, "/".join(VALID_REL_TYPE)))
        if not r.get("label"):
            report.warn("S0", "关系 %s 缺少 label" % r.get("id"))
        # I10
        if dst in page_by_id and rtype in ("route", "modal"):
            target = page_by_id[dst]
            if rtype == "route" and target.get("frame") != "route":
                report.error("I10", "关系 %s 是 route，但目标页 %s 的 frame=%r（应为 route）"
                             % (r.get("id"), dst, target.get("frame")))
            if rtype == "modal":
                if target.get("frame") != "modal":
                    report.error("I10", "关系 %s 是 modal，但目标页 %s 的 frame=%r（应为 modal）"
                                 % (r.get("id"), dst, target.get("frame")))
                if target.get("hostPageId") != src:
                    report.error("I10", "关系 %s 是 modal，但目标页 %s 的 hostPageId=%r 应为源页 %r"
                                 % (r.get("id"), dst, target.get("hostPageId"), src))

    # modal 页必须有 hostPageId
    for p in pages:
        if isinstance(p, dict) and p.get("frame") == "modal" and not p.get("hostPageId"):
            report.error("I10", "页面 %s 是 modal 但缺少 hostPageId" % p.get("id"))

    # ---------- components：I4 / I9 ----------
    comp_ids = {}
    for i, c in enumerate(components):
        label = "components[%d]" % i
        if not isinstance(c, dict):
            report.error("S0", "%s 必须是对象" % label)
            continue
        _check_id(report, "I4", c.get("id"), label, comp_ids)
        used_by = c.get("usedBy")
        if not isinstance(used_by, list):
            report.error("S0", "%s 缺少 usedBy 数组" % label)
            continue
        for pid in used_by:
            # I9
            if pid not in page_by_id:
                report.error("I9", "组件 %s 的 usedBy 引用了不存在的页面：%r" % (c.get("id"), pid))

    # ---------- design：I11 ----------
    # design 块是「可选的」——渲染器允许先定契约后补图，只声明不落盘是常态，
    # 那时它降级渲染（不挂徽标、组件页出骨架）。但降级与「路径写错」长得一模一样，
    # 全靠人眼分辨：所以未渲染时给 WARN，--strict（出图后的门禁）给 ERROR。
    #
    # 逐字段的「必须有」不设：渲染器自己也不要求四个字段齐备（tokens/components
    # 是产品自带就复用、不自带就用内置的资产，缺了是正常形态）。只核两件事——
    # 声明了的字段指向真实文件；以及 spec/states 一个都没有时给一句提醒，
    # 因为那意味着徽标永远挂不上（渲染器判「接上了」看的正是这两份文档）。
    design = manifest.get("design")
    if design is not None:
        if not isinstance(design, dict):
            report.error("I11", "design 必须是对象（{spec, states, tokens, components}）")
        else:
            # 与 render_manifest.py 的 DESIGN_FIELDS 对齐：那四个字段渲染器都认
            known = {"spec", "states", "tokens", "components"}
            fields = {"spec": "设计基线说明", "states": "组件×状态契约",
                      "tokens": "设计 token", "components": "共享组件脚本"}
            for key, val in design.items():
                what = fields.get(key, key)
                if not isinstance(val, str) or not val.strip():
                    report.error("I11", "design.%s 必须是非空字符串：%r" % (key, val))
                    continue
                rel = val.strip()
                if os.path.isfile(os.path.join(root, rel)):
                    continue
                msg = ("design.%s 声明的文件不存在：%s（%s）。若并非「尚未撰写」而是"
                       "路径写错，渲染器会静默降级——页面不挂徽标、组件页出骨架，"
                       "而其余门禁一路绿灯" % (key, rel, what))
                if strict:
                    report.error("I11", msg)
                else:
                    report.warn("I11", msg)
            if not (design.get("spec") or design.get("states")):
                report.warn("I11", "design 只有 tokens/components，没有 spec/states——"
                                   "渲染器判「接上了设计基线」看的正是这两份文档，"
                                   "页面不会挂徽标、组件页只出骨架")
            extra = set(design) - known
            if extra:
                report.warn("I11", "design 含未知字段：%s" % ", ".join(sorted(extra)))

    # ---------- scenes：I4 / I12 ----------
    # scenes[] 是「客户演示档」的场景清单（第三产出档，渲染成 console.html，
    # 见 jf-uxprompt）。整块**可选**——没声明就不校验（同 I11 对 design 块的处理）。
    # 声明了就是纯 ERROR、**不分级**：I11 之所以分级，是因为「design 声明的文件
    # 未落盘是常态」；scenes[] 没有这个性质，写错了就是写错了。
    #
    # I12 是「无来源的界面内容不得入演示框架」的门禁化。原有各条里，I1–I11 管
    # manifest 的结构自洽（I11 最远够到「design 声明的文件在不在」）、F1–F4 管文件
    # 与链接——没有一条要求「演示框架里的东西能追溯到上游」，source 必填补的就是它。
    #
    # 场景 ≠ 笛卡尔积：steps[].state 必须落在该页真实声明的 states 里，于是
    # 「每页 × 全状态」的遍历式组合会因为「业务上不存在这个状态」而写不出来。
    scenes = manifest.get("scenes")
    if scenes is not None:
        if not isinstance(scenes, list):
            report.error("I12", "scenes 必须是数组")
        else:
            scene_ids = {}
            for i, sc in enumerate(scenes):
                label = "scenes[%d]" % i
                if not isinstance(sc, dict):
                    report.error("I12", "%s 必须是对象" % label)
                    continue
                _check_id(report, "I4", sc.get("id"), label, scene_ids)
                if sc.get("id"):
                    label = "场景 %s" % sc["id"]
                title = sc.get("title")
                if not isinstance(title, str) or not title.strip():
                    report.error("I12", "%s 缺少 title" % label)
                elif CODE_REF_RE.search(title):
                    report.error("I12", "%s 的 title=%r 含 FR/AC/BR/SM/UC 编号——"
                                       "title 是给客户看的场景名，编号属 PM 内部语言；"
                                       "编号写进 source，两者分工不同" % (label, title))
                src = sc.get("source")
                if not isinstance(src, str) or not src.strip():
                    report.error("I12", "%s 缺少 source——演示框架里的每个场景都必须"
                                       "能追溯到 MRD/PRD/IA 的具体块"
                                       "（无来源的界面内容不得入演示框架）" % label)
                if sc.get("moduleId") not in module_ids:
                    report.error("I12", "%s 的 moduleId=%r 不存在"
                                 % (label, sc.get("moduleId")))
                steps = sc.get("steps")
                if not isinstance(steps, list) or not steps:
                    report.error("I12", "%s 的 steps 必须是非空数组" % label)
                    continue
                for j, st in enumerate(steps):
                    slabel = "%s 的第 %d 步" % (label, j + 1)
                    if not isinstance(st, dict):
                        report.error("I12", "%s 必须是对象" % slabel)
                        continue
                    tpid = st.get("pageId")
                    if tpid not in page_by_id:
                        report.error("I12", "%s 的 pageId=%r 不存在" % (slabel, tpid))
                        continue
                    state = st.get("state")
                    if not state:
                        report.error("I12", "%s 缺少 state" % slabel)
                        continue
                    known_states = page_by_id[tpid].get("states") or []
                    if state not in known_states:
                        report.error("I12", "%s 的 state=%r 不在页面 %s 声明的 states 里"
                                           "（%s）——场景不是「每页 × 全状态」的遍历，"
                                           "只演示业务上真实会发生的那几个"
                                     % (slabel, state, tpid,
                                        " / ".join(str(s) for s in known_states) or "空"))

    # ---------- annotations ----------
    anns = manifest.get("annotations")
    if anns is not None:
        if not isinstance(anns, dict):
            report.error("S0", "annotations 必须是 {pageId: [annotation]} 对象")
        else:
            seen_numbers = {}
            for pid, items in anns.items():
                if pid not in page_by_id:
                    report.error("S0", "annotations 的 key %r 不是已声明的页面" % pid)
                    continue
                if not isinstance(items, list):
                    report.error("S0", "annotations[%r] 必须是数组" % pid)
                    continue
                nums = seen_numbers.setdefault(pid, set())
                ids = set()
                for a in items:
                    if not isinstance(a, dict):
                        report.error("S0", "annotations[%r] 的元素必须是对象" % pid)
                        continue
                    if not a.get("target"):
                        report.error("S0", "标注 %s 缺少 target（禁止依赖 nth-child / 显示文案）"
                                     % a.get("id"))
                    aid = a.get("id")
                    if isinstance(aid, str) and aid:
                        if aid in ids:
                            report.error("S0", "annotations[%r] 的 id %r 重复——气泡 id 由它派生，"
                                               "同一页内重名会让两条标注指向同一个气泡"
                                         % (pid, aid))
                        ids.add(aid)
                    st = a.get("status")
                    if st is not None and st not in VALID_ANNOTATION_STATUS:
                        report.error("S0", "标注 %s 的 status=%r 不合法"
                                     "（只允许 %s；缺省视作 active）"
                                     % (a.get("id"), st, " / ".join(VALID_ANNOTATION_STATUS)))
                    n = a.get("number")
                    if isinstance(n, int):
                        if n in nums:
                            report.error("S0", "annotations[%r] 的 number %d 重复（删除旧标注不复用编号）"
                                         % (pid, n))
                        nums.add(n)

    # ---------- F1/F2/F3：文件与 HTML 级 ----------
    html_cache = {}

    def read_html(pid):
        if pid in html_cache:
            return html_cache[pid]
        p = page_by_id.get(pid) or {}
        rel = p.get("file")
        text = None
        if rel:
            path = os.path.join(root, rel)
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        text = f.read()
                except OSError as e:
                    report.warn("F1", "页面 %s 的 HTML 读取失败：%s" % (pid, e))
        html_cache[pid] = text
        return text

    for p in pages:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        pid = p["id"]
        rel = p.get("file")
        if not rel:
            continue
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            msg = "页面 %s 声明的 file 不存在：%s" % (pid, rel)
            if strict:
                report.error("F1", msg)
            else:
                report.warn("F1", msg + "（未渲染；渲染后必须存在）")

    # F2：HTML 内 data-nav 指向不存在的页面
    for p in pages:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        pid = p["id"]
        html = read_html(pid)
        if html is None:
            continue
        for href, nav in parse_anchors(html):
            if nav and nav not in page_by_id:
                report.error("F2", "页面 %s 的 HTML 中 data-nav=%r 指向不存在的页面" % (pid, nav))

    # F3：relation 声明的跳转在源页 HTML 中找不到对应链接
    for r in relations:
        if not isinstance(r, dict):
            continue
        src, dst, rtype = r.get("from"), r.get("to"), r.get("type")
        if rtype != "route" and rtype != "modal":
            continue
        if src not in page_by_id or dst not in page_by_id:
            continue
        # sub-flow 源页的链接可能渲染在自身或宿主页的「从属与跳转」区，两处任一命中即算通过
        carriers = [src]
        src_page = page_by_id[src]
        if src_page.get("nav") == "sub-flow" and src_page.get("hostPageId"):
            carriers.append(src_page["hostPageId"])
        target_file = page_by_id[dst].get("file")
        target_base = os.path.basename(target_file or "")
        found = False
        for carrier in carriers:
            html = read_html(carrier)
            if html is None:
                continue
            for href, nav in parse_anchors(html):
                if nav == dst:
                    found = True
                    break
                if href and target_base and nav_target(href) == target_base:
                    found = True
                    break
            if found:
                break
        if not found:
            msg = "关系 %s（%s → %s）在 %s 的 HTML 中找不到对应链接" \
                  % (r.get("id"), src, dst, " / ".join(carriers))
            if strict:
                report.error("F3", msg)
            else:
                report.warn("F3", msg)

    # F3（反向）：页面中的跳转链接必须能在 relations[] 中找到声明
    # （侧边导航属结构性链接、「由谁激活」的宿主回链属结构性回链，均豁免）
    declared_pairs = {(r.get("from"), r.get("to"))
                      for r in relations if isinstance(r, dict)}
    basename_to_pid = {}
    for p in pages:
        if isinstance(p, dict) and p.get("id") and p.get("file"):
            basename_to_pid[os.path.basename(p["file"])] = p["id"]
    for p in pages:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        pid = p["id"]
        page_html = read_html(pid)
        if page_html is None:
            continue
        host = p.get("hostPageId")
        for href, nav in parse_anchors(strip_nav_block(page_html)):
            tid = nav
            if not tid and href:
                tid = basename_to_pid.get(nav_target(href))
            if not tid or tid == pid or tid not in page_by_id:
                continue
            if tid == host:
                continue
            if (pid, tid) not in declared_pairs:
                msg = "页面 %s 的链接指向 %s，但 relations[] 未声明该跳转" % (pid, tid)
                if strict:
                    report.error("F3", msg)
                else:
                    report.warn("F3", msg)

    # F4：标注 target 必须能定位到页面 HTML 中的真实元素
    if isinstance(anns, dict):
        for pid, items in anns.items():
            if pid not in page_by_id or not isinstance(items, list):
                continue
            page_html = read_html(pid)
            for a in items:
                if not isinstance(a, dict):
                    continue
                target = a.get("target") or ""
                label = "标注 %s" % a.get("id", "?")
                if ":nth" in target or target.startswith("text="):
                    report.error("F4", "%s 的 target=%r 违反标注协议"
                                 "（禁止依赖 nth-child / 显示文案）" % (label, target))
                    continue
                if page_html is None:
                    report.warn("F4", "%s 的 target=%r 所在页面尚未渲染，暂无法核对"
                                % (label, target))
                    continue
                hit = annotation_target_in_html(target, page_html)
                if hit is None:
                    report.error("F4", "%s 的 target=%r 无法解析"
                                 "（标注协议只允许 #id 与 [data-annotation-anchor=值]）"
                                 % (label, target))
                elif not hit:
                    report.error("F4", "%s 的 target=%r 在页面 %s 的 HTML 中"
                                 "找不到对应元素" % (label, target, pid))

    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def is_failed(report: Report, strict: bool) -> bool:
    """是否未通过：有 ERROR 即未通过；--strict 下有 WARN 也未通过。"""
    return bool(report.errors) or (strict and bool(report.warnings))


def render_text(report: Report, manifest_path: str, strict: bool) -> str:
    lines = []
    lines.append("校验对象：%s" % manifest_path)
    lines.append("")
    if not report.issues:
        lines.append("✅ 全部通过，无问题。")
        return "\n".join(lines)
    if report.errors:
        lines.append("❌ 错误 %d 条：" % len(report.errors))
        lines.extend(str(i) for i in report.errors)
        lines.append("")
    if report.warnings:
        lines.append("⚠️  警告 %d 条%s：" % (len(report.warnings),
                                            "（--strict 下视为错误）" if strict else ""))
        lines.extend(str(i) for i in report.warnings)
        lines.append("")
    if not report.errors:
        lines.append("✅ 无错误%s。" % ("；但有 %d 条警告" % len(report.warnings) if report.warnings else ""))
    return "\n".join(lines)


def load_manifest(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# 自检样例
# --------------------------------------------------------------------------- #

def _valid_sample():
    return {
        "schemaVersion": 1,
        "product": {"name": "XX系统", "type": "Web",
                    "source": {"mrd": "docs/x-mrd.md", "prd": "docs/x-prd.md"}},
        "modules": [{"id": "demand", "title": "需求管理", "kind": "prd", "navNumber": "01"}],
        "pages": [
            {"id": "demand-list", "title": "需求列表", "moduleId": "demand",
             "file": "prototypes/pages/demand-list.html", "kind": "list",
             "nav": "standalone", "frame": "route", "obj": "需求项目", "crud": "R",
             "device": "desktop", "viewport": {"width": 1440, "height": 900},
             "states": ["default", "empty", "loading", "error"], "hostPageId": None,
             "fr": ["FR-05"]},
            {"id": "demand-detail", "title": "需求详情", "moduleId": "demand",
             "file": "prototypes/pages/demand-detail.html", "kind": "detail",
             "nav": "standalone", "frame": "route", "obj": "需求项目", "crud": "RU",
             "device": "desktop", "viewport": {"width": 1440, "height": 900},
             "states": ["default", "loading"], "hostPageId": None, "fr": ["FR-06"]},
            {"id": "demand-upload", "title": "材料上传", "moduleId": "demand",
             "file": "prototypes/pages/demand-upload.html", "kind": "form",
             "nav": "sub-flow", "frame": "route", "obj": "材料", "crud": "C",
             "hostPageId": "demand-detail", "device": "desktop",
             "viewport": {"width": 1440, "height": 900},
             "states": ["default", "error"], "fr": ["FR-11"]},
        ],
        "relations": [
            {"id": "r-list-detail", "from": "demand-list", "to": "demand-detail",
             "label": "查看详情", "type": "route", "semantic": "drill",
             "trigger": "[data-nav=demand-detail]", "condition": "行点击"},
            {"id": "r-detail-upload", "from": "demand-detail", "to": "demand-upload",
             "label": "上传材料", "type": "route", "semantic": "activate"},
        ],
        "components": [
            {"id": "page-shell", "title": "页面外壳",
             "usedBy": ["demand-list", "demand-detail"]},
        ],
    }


def _invalid_sample():
    return {
        "schemaVersion": 1,
        "product": {"name": "XX系统", "type": "Web"},
        "modules": [{"id": "demand", "title": "需求管理"},
                    {"id": "orphan", "title": "无人引用模块"}],
        "pages": [
            {"id": "demand-list", "title": "需求列表", "moduleId": "demand",
             "file": "prototypes/pages/wrong-name.html",  # I1
             "kind": "list", "nav": "standalone", "frame": "route",
             "obj": "需求项目", "crud": "RD",  # I7（无 crudNote）
             "device": "tablet",  # I5
             "viewport": {"width": 0, "height": 900},  # I5
             "states": ["loading"],  # I8（无 default）
             "hostPageId": None},
            {"id": "Demand_Detail", "title": "需求详情", "moduleId": "demand",  # I4
             "file": "prototypes/pages/demand-detail.html", "kind": "detail",
             "nav": "sub-flow", "frame": "route",  # I3（无 hostPageId）
             "obj": "需求项目", "crud": "R", "device": "desktop",
             "viewport": {"width": 1440, "height": 900}, "states": ["default"]},
            {"id": "demand-list", "title": "重复 id", "moduleId": "demand",  # I4 重复
             "file": "prototypes/pages/demand-list.html", "kind": "list",
             "nav": "standalone", "frame": "route", "obj": "需求项目", "crud": "R",
             "device": "desktop", "viewport": {"width": 1440, "height": 900},
             "states": ["default"]},
        ],
        "relations": [
            {"id": "r-ghost", "from": "demand-list", "to": "no-such-page",  # I2
             "label": "幽灵跳转", "type": "route"},
            {"id": "r-bad-modal", "from": "demand-list", "to": "Demand_Detail",  # I10
             "label": "错标弹窗", "type": "modal"},
        ],
        "components": [
            {"id": "page-shell", "title": "页面外壳", "usedBy": ["ghost-page"]},  # I9
        ],
    }


def self_test() -> int:
    print("=== validate_manifest.py 自检 ===")
    ok = True

    with tempfile.TemporaryDirectory() as td:
        # 1) 合法样例：期望 0 error
        vpath = os.path.join(td, "valid.json")
        with open(vpath, "w", encoding="utf-8") as f:
            json.dump(_valid_sample(), f, ensure_ascii=False)
        rep = validate(_valid_sample(), root=td, strict=False)
        if rep.errors:
            ok = False
            print("❌ 合法样例应无 ERROR，实际 %d 条：" % len(rep.errors))
            for i in rep.errors:
                print(i)
        else:
            print("✅ 合法样例：0 error（警告 %d 条，均为未渲染的文件缺失）" % len(rep.warnings))

        # 2) 非法样例：期望逐条报出指定规则码
        ipath = os.path.join(td, "invalid.json")
        with open(ipath, "w", encoding="utf-8") as f:
            json.dump(_invalid_sample(), f, ensure_ascii=False)
        rep2 = validate(_invalid_sample(), root=td, strict=False)
        codes = {i.code for i in rep2.errors}
        expected = {"I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9", "I10"}
        missing = expected - codes
        if missing:
            ok = False
            print("❌ 非法样例未报出的规则码：%s" % ", ".join(sorted(missing)))
        else:
            print("✅ 非法样例：I1–I10 全部命中（共 %d 条错误）" % len(rep2.errors))

        # 3) strict 模式：文件缺失应升级为 ERROR
        rep3 = validate(_valid_sample(), root=td, strict=True)
        f1_errors = [i for i in rep3.errors if i.code == "F1"]
        if not f1_errors:
            ok = False
            print("❌ --strict 应把未渲染的文件缺失（F1）升级为 ERROR")
        else:
            print("✅ --strict：F1 文件缺失升级为 ERROR（%d 条）" % len(f1_errors))

        # 4) F4：标注 target 存在性（缺失 / nth-child 违规 / 合法不误报）
        pages_dir = os.path.join(td, "prototypes", "pages")
        os.makedirs(pages_dir, exist_ok=True)
        with open(os.path.join(pages_dir, "demand-list.html"), "w",
                  encoding="utf-8") as f:
            f.write('<!DOCTYPE html><html><body>'
                    '<button id="btn-real">新增</button></body></html>')
        m4 = _valid_sample()
        m4["annotations"] = {"demand-list": [
            {"id": "a-1", "number": 1, "target": "#btn-real"},
            {"id": "a-2", "number": 2, "target": "#btn-missing"},
            {"id": "a-3", "number": 3, "target": "tbody tr:nth-child(2)"},
        ]}
        rep4 = validate(m4, root=td, strict=False)
        f4_msgs = [i.message for i in rep4.errors if i.code == "F4"]
        if (any("btn-missing" in x for x in f4_msgs)
                and any(":nth" in x or "nth" in x for x in f4_msgs)
                and not any("btn-real" in x for x in f4_msgs)):
            print("✅ F4：target 缺失与 nth-child 违规均报出，合法 target 不误报")
        else:
            ok = False
            print("❌ F4 校验不符预期：%s" % "; ".join(f4_msgs))

        # 4b) 标注 status 词表：非法值报 S0，三态与缺省都不报
        m4b = _valid_sample()
        m4b["annotations"] = {"demand-list": [
            {"id": "a-1", "number": 1, "target": "#btn-real", "status": "active"},
            {"id": "a-2", "number": 2, "target": "#btn-real", "status": "resolved"},
            {"id": "a-3", "number": 3, "target": "#btn-real", "status": "rejected"},
            {"id": "a-4", "number": 4, "target": "#btn-real"},  # 缺省 = active
            {"id": "a-5", "number": 5, "target": "#btn-real", "status": "done"},
        ]}
        rep4b = validate(m4b, root=td, strict=False)
        s0_msgs = [i.message for i in rep4b.errors if i.code == "S0"]
        if (any("a-5" in x and "done" in x for x in s0_msgs)
                and not any("a-1" in x or "a-2" in x or "a-3" in x or "a-4" in x
                            for x in s0_msgs)):
            print("✅ status 词表：三态与缺省通过，非法值报 S0")
        else:
            ok = False
            print("❌ status 词表校验不符预期：%s" % "; ".join(s0_msgs))

        # 4c) 同页标注 id 唯一：重名报 S0，跨页同名不报（气泡 id 带 pageId 前缀）
        m4c = _valid_sample()
        m4c["annotations"] = {
            "demand-list": [
                {"id": "dup", "number": 1, "target": "#btn-real"},
                {"id": "dup", "number": 2, "target": "#btn-real"},
                {"id": "", "number": 3, "target": "#btn-real"},  # 无 id 不参与查重
            ],
            "demand-detail": [{"id": "dup", "number": 1, "target": "#btn-real"}],
        }
        rep4c = validate(m4c, root=td, strict=False)
        dup_msgs = [i.message for i in rep4c.errors if i.code == "S0"]
        if (len(dup_msgs) == 1 and "dup" in dup_msgs[0] and "demand-list" in dup_msgs[0]
                and not any("demand-detail" in x for x in dup_msgs)):
            print("✅ 标注 id 唯一：同页重名报 S0，跨页同名与空 id 不误报")
        else:
            ok = False
            print("❌ 标注 id 唯一性校验不符预期：%s" % "; ".join(dup_msgs))

        # 5) --strict 下警告计入退出判定（rep 无 ERROR、有 F1 警告）
        if is_failed(rep, strict=False):
            ok = False
            print("❌ 默认模式下仅警告应算通过")
        elif not is_failed(rep, strict=True):
            ok = False
            print("❌ --strict 下仅警告应算未通过")
        else:
            print("✅ 退出码：默认仅警告通过，--strict 下警告也算失败")

        # 6) F3 反向：全部 <nav> 块都要剔除（多 nav / 移动端抽屉导航）
        #    抽屉里的链接若未剔除，会被误判成「relations 未声明的跳转」
        nav_root = os.path.join(td, "navtest")
        nav_pages = os.path.join(nav_root, "prototypes", "pages")
        os.makedirs(nav_pages, exist_ok=True)
        m6 = _valid_sample()
        m6["pages"] = m6["pages"] + [{
            "id": "demand-archive", "title": "归档确认", "moduleId": "demand",
            "file": "prototypes/pages/demand-archive.html", "kind": "detail",
            "nav": "standalone", "frame": "route", "obj": "需求项目", "crud": "R",
            "device": "desktop", "viewport": {"width": 1440, "height": 900},
            "states": ["default"], "hostPageId": None}]
        drawer = ('<nav class="jf-nav jf-drawer">'
                  '<a href="demand-archive.html" data-nav="demand-archive">归档</a></nav>')
        with open(os.path.join(nav_pages, "demand-list.html"), "w",
                  encoding="utf-8") as f:
            f.write('<!DOCTYPE html><html><body>'
                    '<nav class="jf-nav">'
                    '<a href="demand-detail.html" data-nav="demand-detail">详情</a></nav>'
                    '<main><a href="demand-detail.html" data-nav="demand-detail">看详情</a></main>'
                    + drawer + '</body></html>')
        rep6 = validate(m6, root=nav_root, strict=False)
        ghost = [i.message for i in rep6.issues
                 if i.code == "F3" and "demand-list 的链接指向 demand-archive" in i.message]
        if ghost:
            ok = False
            print("❌ 第二个 <nav> 块未被剔除，抽屉导航被误判为未声明跳转：%s" % ghost[0])
        else:
            print("✅ F3 反向：多个 <nav> 块全部剔除，抽屉导航不误报")

        # 7) F3 反向对照组：同一条链接挪到正文里必须照报（剔除范围只限 nav）
        with open(os.path.join(nav_pages, "demand-list.html"), "w",
                  encoding="utf-8") as f:
            f.write('<!DOCTYPE html><html><body>'
                    '<nav class="jf-nav">'
                    '<a href="demand-detail.html" data-nav="demand-detail">详情</a></nav>'
                    '<main><a href="demand-archive.html" data-nav="demand-archive">归档</a></main>'
                    '</body></html>')
        rep7 = validate(m6, root=nav_root, strict=False)
        if not any(i.code == "F3" and "demand-list 的链接指向 demand-archive" in i.message
                   for i in rep7.issues):
            ok = False
            print("❌ 正文里未声明的跳转未被报出（剔除范围过大）")
        else:
            print("✅ F3 反向对照组：正文里未声明的跳转照报，nav 豁免未越界")

        # 8) I11：design 块。默认模式容忍「先定契约后补图」，--strict 必须报错；
        #    否则 design.spec 写成 DESIGN-typo.md 会静默降级成「没有设计基线」，
        #    页面不挂徽标、组件页只出骨架，而全部门禁一路绿灯。
        dg_root = os.path.join(td, "designtest")
        os.makedirs(dg_root, exist_ok=True)
        m8 = _valid_sample()
        m8["design"] = {"spec": "DESIGN-typo.md",
                        "states": "components-and-states.md",
                        "tokens": "prototypes/shared/tokens.css"}
        for name in ("components-and-states.md",):
            with open(os.path.join(dg_root, name), "w", encoding="utf-8") as f:
                f.write("# 占位\n")
        rep8_loose = validate(m8, root=dg_root, strict=False)
        rep8_strict = validate(m8, root=dg_root, strict=True)
        loose11 = [i for i in rep8_loose.issues if i.code == "I11"]
        strict11 = [i.message for i in rep8_strict.errors if i.code == "I11"]
        if not loose11 or any(i.level == ERROR for i in loose11):
            ok = False
            print("❌ design 文件缺失在默认模式下应为 WARN（先定契约后补图是常态）")
        elif not any("DESIGN-typo.md" in x for x in strict11):
            ok = False
            print("❌ --strict 未把 design 路径写错升级为 ERROR：%s" % strict11)
        elif any("components-and-states.md" in x for x in strict11):
            ok = False
            print("❌ 存在的 design 文件被误报：%s" % strict11)
        else:
            print("✅ I11：design 路径写错——默认 WARN、--strict ERROR，存在的不误报")

        # 8b) I11：design 类型不对 / 字段是空串 / 未知字段
        m8b = _valid_sample()
        m8b["design"] = {"spec": 123, "states": "  ", "tokens": "prototypes/shared/tokens.css",
                         "skin": "extra"}
        rep8b = validate(m8b, root=dg_root, strict=False)
        msgs8b = "\n".join(i.message for i in rep8b.issues if i.code == "I11")
        if ("design.spec" in msgs8b and "design.states" in msgs8b
                and "未知字段" in msgs8b):
            print("✅ I11：非字符串 / 空串 / 未知字段均报出")
        else:
            ok = False
            print("❌ I11 未覆盖非字符串/空串/未知字段：%s" % msgs8b)

        # 8c) I11：只有 tokens/components 时提醒——渲染器判「接上了设计基线」
        #     看的是 spec/states，这两个缺了徽标永远挂不上，而别的门禁不会说话。
        #     同时确认：不声明的字段（这里是组件脚本）不报「必须有」——
        #     产品自带就复用、不自带用内置，缺了本就是正常形态。
        m8c = _valid_sample()
        m8c["design"] = {"tokens": "prototypes/shared/tokens.css"}
        os.makedirs(os.path.join(dg_root, "prototypes", "shared"), exist_ok=True)
        with open(os.path.join(dg_root, "prototypes", "shared", "tokens.css"), "w",
                  encoding="utf-8") as f:
            f.write(":root{}\n")
        rep8c = validate(m8c, root=dg_root, strict=False)
        msgs8c = [i.message for i in rep8c.issues if i.code == "I11"]
        if not any("spec/states" in x for x in msgs8c):
            ok = False
            print("❌ design 只有 tokens 时应提醒徽标挂不上：%s" % msgs8c)
        elif any("必须有" in x or "缺少" in x for x in msgs8c):
            ok = False
            print("❌ 未声明的字段不该报「必须有」（渲染器本就不要求齐备）：%s" % msgs8c)
        else:
            print("✅ I11：只有 tokens 时提醒徽标挂不上；未声明的字段不报「必须有」")

        # 9) I12：场景清单——合法的不该误报
        m9 = _valid_sample()
        m9["scenes"] = [
            {"id": "score-limit", "moduleId": "demand", "title": "基础积分达上限",
             "source": "AC-05-3", "flow": "月度打分",
             "steps": [{"pageId": "demand-list", "state": "empty", "label": "首次无数据"},
                       {"pageId": "demand-detail", "state": "default", "label": "查看详情"}]},
        ]
        i12_9 = [i.message for i in validate(m9, root=td).errors if i.code == "I12"]
        if i12_9:
            ok = False
            print("❌ 合法 scenes 不该报 I12：%s" % i12_9)
        else:
            print("✅ I12：合法场景（source 齐全、state 落在页面 states 里）不误报")

        # 10) I12：五类非法各报一条
        m10 = _valid_sample()
        m10["scenes"] = [
            {"id": "s-nosource", "moduleId": "demand", "title": "缺来源场景",
             "steps": [{"pageId": "demand-list", "state": "default"}]},
            {"id": "s-badstate", "moduleId": "demand", "title": "状态不存在",
             "source": "BR-01",
             "steps": [{"pageId": "demand-list", "state": "success"}]},
            {"id": "s-coded", "moduleId": "demand", "title": "基础积分达上限AC-05-3",
             "source": "AC-05-3",
             "steps": [{"pageId": "demand-list", "state": "default"}]},
            {"id": "s-ghostmod", "moduleId": "no-such", "title": "模块不存在",
             "source": "UC-01",
             "steps": [{"pageId": "demand-list", "state": "default"}]},
            {"id": "s-ghostpage", "moduleId": "demand", "title": "页面不存在",
             "source": "UC-02",
             "steps": [{"pageId": "no-such-page", "state": "default"}]},
        ]
        msgs10 = [i.message for i in validate(m10, root=td).errors if i.code == "I12"]
        missing10 = [desc for want, desc in (
            ("缺少 source", "source 缺失"),
            ("不在页面 demand-list 声明的 states 里", "state 越界"),
            ("含 FR/AC/BR/SM/UC 编号", "title 含编号"),
            ("moduleId='no-such' 不存在", "moduleId 不存在"),
            ("pageId='no-such-page' 不存在", "pageId 不存在"))
            if not any(want in x for x in msgs10)]
        if missing10:
            ok = False
            print("❌ I12 未报出：%s\n   实际：%s" % ("、".join(missing10), msgs10))
        else:
            print("✅ I12：source 缺失 / state 越界 / title 含编号 / moduleId / pageId 五类均报出")

        # 11) href 归一化：`?state=` 是同一个跳转目标，不是另一个页面
        nav_root = os.path.join(td, "href-nav")
        nav_pages = os.path.join(nav_root, "prototypes", "pages")
        os.makedirs(nav_pages, exist_ok=True)
        m11 = _valid_sample()
        m11["relations"] = [{"id": "r-list-detail", "from": "demand-list",
                             "to": "demand-detail", "label": "查看详情", "type": "route"}]
        # 只有 href、没有 data-nav——逼 F3 走 basename 比对那条路
        with open(os.path.join(nav_pages, "demand-list.html"), "w", encoding="utf-8") as f:
            f.write('<a href="./demand-detail.html?state=error">看详情</a>')
        with open(os.path.join(nav_pages, "demand-detail.html"), "w", encoding="utf-8") as f:
            f.write('<a href="./demand-upload.html?state=error">上传材料</a>')
        with open(os.path.join(nav_pages, "demand-upload.html"), "w", encoding="utf-8") as f:
            f.write("<p>材料上传</p>")
        f3_msgs = [i.message for i in validate(m11, root=nav_root).issues if i.code == "F3"]
        if any("demand-detail" in x and "找不到对应链接" in x for x in f3_msgs):
            ok = False
            print("❌ 带 ?state= 的 href 被误判成「找不到对应链接」：%s" % f3_msgs)
        elif not any("demand-upload" in x for x in f3_msgs):
            ok = False
            print("❌ 带 ?state= 的 href 指向未声明跳转，F3 应报出却静默跳过：%s" % f3_msgs)
        else:
            print("✅ href 归一化：?state= 不再让 F3 误判，也不再让未声明跳转漏网")

    print("=== 自检%s ===" % ("通过" if ok else "失败"))
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="校验 jf-* manifest.json 契约（I1–I12 + F1–F4）")
    parser.add_argument("manifest", nargs="?", help="manifest.json 路径")
    parser.add_argument("--root", default=None,
                        help="pages[].file 的相对根目录，默认 manifest 所在目录")
    parser.add_argument("--strict", action="store_true",
                        help="把 WARN 视为 ERROR（S0/I11/F1/F3/F4 的提示全部判失败）")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="输出机读 JSON 报告")
    parser.add_argument("--self-test", action="store_true",
                        help="用内置合法/非法样例验证脚本本身")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.manifest:
        parser.print_help()
        return 2

    path = os.path.abspath(args.manifest)
    if not os.path.isfile(path):
        print("找不到 manifest：%s" % path, file=sys.stderr)
        return 2
    try:
        manifest = load_manifest(path)
    except (OSError, ValueError) as e:
        print("manifest 解析失败：%s" % e, file=sys.stderr)
        return 2

    root = args.root or os.path.dirname(path)
    report = validate(manifest, root=root, strict=args.strict)

    if args.as_json:
        print(json.dumps({
            "manifest": path,
            "passed": not is_failed(report, args.strict),
            "errorCount": len(report.errors),
            "warningCount": len(report.warnings),
            "issues": [i.as_dict() for i in report.issues],
        }, ensure_ascii=False, indent=2))
    else:
        print(render_text(report, path, args.strict))

    return 1 if is_failed(report, args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
