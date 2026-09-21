#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_design.py — jf-design 设计基线校验门禁（G1–G8）

校验 manifest.design 指向的 DESIGN.md（三层 token）、components-and-states.md
（组件×状态）与 prototypes/shared/tokens.css（三层落地）是否满足设计基线契约。
契约全文见：
  products/jiaofu/jf-design/references/design-contract.md

用法：
  python3 check_design.py <manifest.json> [--root DIR] [--json]
  python3 check_design.py --self-test        # 用内置合法/非法样例验证脚本本身

退出码：
  0  通过（无 ERROR；WARN 仍算通过）
  1  未通过（存在 ERROR）
  2  用法错误 / manifest 无法解析
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

ERROR = "ERROR"
WARN = "WARN"

# 四态 + 跨模块五状态（与 design-contract.md 一致）
COMPONENT_STATES = ("default", "hover", "active", "disabled")
CROSS_STATES = ("empty", "loading", "error", "disabled", "permission-denied")

# DESIGN.md 必含段落：段落名 → 标题行内的识别关键词（命中任一即算）
REQUIRED_SECTIONS = [
    ("产品基调", ("基调",)),
    ("色板（primitive）", ("色板", "primitive")),
    ("字体与字阶", ("字体", "字阶")),
    ("间距/圆角/阴影栅格", ("间距", "圆角", "栅格")),
    ("语义变量（semantic）", ("语义变量", "semantic")),
    ("组件变量（component）", ("组件变量", "component")),
    ("明确排除项", ("排除",)),
]
SEMANTIC_KEYWORDS = ("语义变量", "semantic")
COMPONENT_VAR_KEYWORDS = ("组件变量", "component")
PRIMITIVE_KEYWORDS = ("色板", "primitive")
# primitive 分散在三个段落：色板之外，字体与字阶、间距·圆角·栅格 也是合法来源
FONT_KEYWORDS = ("字体", "字阶")
SPACING_KEYWORDS = ("间距", "圆角", "栅格")

# 裸 hex：#RGB / #RGBA / #RRGGBB / #AARRGGBB，前后不能紧贴字母数字
# （防把 markdown 锚点 #badge、issue 编号 #12345 误判为色值）
HEX_RE = re.compile(
    r"(?<![0-9A-Za-z])#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9A-Za-z])")

CHECK_MARKS = ("✓", "✔", "✅")

# 组件类型：交互组件四态必须全 ✓；容器组件四态可标 —，但必须配落点说明
COMPONENT_KINDS = ("交互", "容器")
# 表下以 `- \`<id>\`：` 开头的落点说明（容器状态的落点写在这里）
CONTAINER_NOTE_RE = re.compile(r"^\s*[-*]\s*`?([A-Za-z0-9_-]+)`?\s*[:：]")

# tokens.css 解析：先剥注释，再取变量声明（同名校后声明覆盖前者）
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
CSS_VAR_RE = re.compile(r"(--jf-[a-z0-9-]+)\s*:\s*([^;]+);")
CODE_SPAN_RE = re.compile(r"`([^`]*)`")
# 单个 var() 引用（整串就是一个引用，才算一层派生；混合值按裸值处理）
VAR_ONLY_RE = re.compile(r"var\(\s*(--jf-[a-z0-9-]+)\s*\)")


def norm_value(v: str) -> str:
    """CSS 取值归一化后比较：统一小写并去掉全部空白。

    DESIGN.md 里写 `rgba(15,23,42,.45)`、tokens.css 里写 `rgba(15, 23, 42, .45)`
    是同一个值，不归一化会误报漂移。
    """
    return re.sub(r"\s+", "", str(v)).lower()


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
# Markdown 解析（只用标准库，按标题切段、竖线切表）
# --------------------------------------------------------------------------- #

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def split_sections(text: str) -> dict:
    """返回 {段落标题: 段落正文行列表}，遇到任意级别标题即切段。"""
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            current = m.group(2)
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def find_section(sections: dict, keywords, exclude=()) -> tuple:
    """按关键词找段落，返回 (标题, 正文行) 或 (None, None)。
    exclude：标题含这些关键词的段落跳过（如查「状态」表时排除「组件×状态」）。"""
    for title, body in sections.items():
        if any(k.lower() in title.lower() for k in keywords) \
                and not any(e in title for e in exclude):
            return title, body
    return None, None


def find_component_table(sections: dict) -> tuple:
    """定位「组件×状态」表，返回 (标题, 正文行) 或 (None, None)。

    不能只用 find_section(("组件",))：契约模板的 H1 标题
    （`# components-and-states.md — <产品名> 组件×状态契约`）本身也含「组件」二字，
    而它的正文里没有表——直接命中标题会误判成「表头缺 id 列」。
    因此优先取「标题含组件且表头带 id 列」的段落；都没有时退回「标题含组件且有表」
    的段落，交给调用方报「表头缺少 id 列」。
    """
    fallback = (None, None)
    for title, body in sections.items():
        if "组件" not in title:
            continue
        rows = table_rows(body)
        if not rows:
            continue
        if "id" in [strip_ticks(h) for h in rows[0]]:
            return title, body
        if fallback[0] is None:
            fallback = (title, body)
    return fallback


def table_rows(body_lines) -> list:
    """抽走表头和分隔行，返回数据行（每行是去空格后的单元格列表）。"""
    rows = []
    for line in body_lines:
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue  # 分隔行 |---|---|
        rows.append(cells)
    return rows


def cell_marked(cell: str) -> bool:
    """四态列是否标了 ✓（— 或空视为缺失）。"""
    c = cell.strip()
    return any(mark in c for mark in CHECK_MARKS)


def strip_ticks(s: str) -> str:
    """去掉 Markdown 行内代码标记：`a` → a。

    一格可能含多个 code span（如「引用 token」列 `--jf-a`、`--jf-b`），
    整串 strip("`") 只吃最外两个反引号，会把中间的留在文本里。
    """
    text = str(s if s is not None else "").strip()
    return CODE_SPAN_RE.sub(r"\1", text).replace("`", "").strip()


# --------------------------------------------------------------------------- #
# 三层落地一致性（G7 / G8）辅助
# --------------------------------------------------------------------------- #

def _declared_tables(sections: dict) -> tuple:
    """DESIGN.md 三张表 → (primitive{名:值}, semantic{变量:引用}, component{变量:引用})。

    三张表的列序由契约模板固定：首列是 token 名，次列是值 / 引用。
    primitive 分散在三个段落（色板 / 字体与字阶 / 间距·圆角·栅格），三处都是合法来源。
    """
    def pairs_of(keywords) -> dict:
        title, body = find_section(sections, keywords)
        pairs = {}
        if title is not None:
            for row in table_rows(body)[1:]:      # 去表头
                if len(row) >= 2 and strip_ticks(row[0]):
                    pairs[strip_ticks(row[0])] = strip_ticks(row[1])
        return pairs

    prim = {}
    for keywords in (PRIMITIVE_KEYWORDS, FONT_KEYWORDS, SPACING_KEYWORDS):
        prim.update(pairs_of(keywords))
    return prim, pairs_of(SEMANTIC_KEYWORDS), pairs_of(COMPONENT_VAR_KEYWORDS)


def as_var(name: str) -> str:
    """DESIGN.md 里的 primitive 名 → CSS 变量名：blue-600 → --jf-blue-600。"""
    return name if name.startswith("--") else "--jf-" + name


def css_vars(text: str) -> dict:
    """tokens.css → {变量名: 取值}（先剥注释，后声明覆盖先声明）。"""
    body = CSS_COMMENT_RE.sub("", text)
    out = {}
    for name, value in CSS_VAR_RE.findall(body):
        out[name] = value.strip()
    return out


def ref_of(value: str):
    """取值的唯一引用：var(--jf-x) → --jf-x；不是纯引用则返回 None。"""
    m = VAR_ONLY_RE.fullmatch(str(value).strip())
    return m.group(1) if m else None


def css_layers(css: dict) -> dict:
    """按取值形状定层 → {变量: primitive|semantic|component|too-deep|dangling|cyclic}。

    这是「三层不越级」的机械判据：无 var() 即裸值（primitive），
    纯引用则取其被引用者的下一层。不依赖注释或 :root 分块——注释不是契约。
    """
    order = ("primitive", "semantic", "component")
    out: dict[str, str] = {}

    def layer(name: str, stack) -> str:
        if name in out:
            return out[name]
        if name in stack:
            return "cyclic"
        if name not in css:
            return "dangling"
        ref = ref_of(css[name])
        if ref is None:
            out[name] = "primitive"
            return "primitive"
        base = layer(ref, stack | {name})
        if base in ("primitive", "semantic"):
            res = order[order.index(base) + 1]
        elif base == "dangling" or base == "cyclic":
            res = base
        else:
            res = "too-deep"                      # component 再引用 component
        out[name] = res
        return res

    for name in css:
        layer(name, frozenset())
    return out


def container_notes(sections: dict) -> set:
    """「组件×状态」表下以 `- \\`<id>\\`：` 开头的落点说明 → 组件 id 集合。"""
    title, body = find_component_table(sections)
    if title is None:
        return set()
    found = set()
    for line in body:
        m = CONTAINER_NOTE_RE.match(line)
        if m:
            found.add(m.group(1))
    return found


def check_token_landing(report: Report, design: dict, root: str,
                        sections: dict, doc_sections: dict) -> None:
    """G7：DESIGN.md ↔ tokens.css 三层落地一致性；G8：表格引用的 token 名可解析。

    DESIGN.md 是 tokens.css 的真相源——两边不一致时以 DESIGN.md 为准，
    但门禁必须把不一致报出来，否则「真相源」名存实亡（此前 tokens.css 完全无人看守：
    把主强调色改成任意色相，G1–G6 全绿）。
    """
    tokens_rel = design.get("tokens")
    if not tokens_rel:
        return                          # 未声明 tokens 落地：不是每个项目都要出 CSS
    tokens_path = os.path.join(root, tokens_rel)
    if not os.path.isfile(tokens_path):
        report.warn("G7", "design.tokens 声明的 %s 不存在"
                          "（渲染器会生成；若本就无 CSS 落地可忽略）" % tokens_rel)
        return
    with open(tokens_path, encoding="utf-8") as f:
        css = css_vars(f.read())
    if not css:
        report.warn("G7", "%s 里没有 --jf-* 变量声明" % tokens_rel)
        return

    prim, sem, comp = _declared_tables(sections)
    # DESIGN.md 的 primitive 名不带 --jf- 前缀（blue-600），CSS 变量带——统一成变量名再比
    prim_decl = {as_var(n): v for n, v in prim.items()}
    layers = css_layers(css)

    # 1) CSS 里每个变量：层要合法，且必须由 DESIGN.md 声明、取值不漂移
    for var, value in sorted(css.items()):
        lyr = layers.get(var)
        ref = ref_of(value)
        if lyr == "dangling":
            report.error("G7", "tokens.css 的 %s 引用了不存在的变量：%s"
                               % (var, value))
        elif lyr == "cyclic":
            report.error("G7", "tokens.css 的 %s 处于循环引用中：%s" % (var, value))
        elif lyr == "too-deep":
            report.error("G7", "tokens.css 的 %s 引用了 component 层变量（%s）——"
                               "三层只有 primitive → semantic → component，不许再往下套"
                               % (var, ref))
        elif lyr == "primitive":
            if var not in prim_decl:
                report.error("G7", "tokens.css 定义了裸值 %s: %s，但 DESIGN.md 的 primitive 段落"
                                   "（色板 / 字体与字阶 / 间距·圆角·栅格）没有声明它"
                                   "（CSS 不得自行发明取值）" % (var, value))
            elif norm_value(prim_decl[var]) != norm_value(value):
                report.error("G7", "tokens.css 的 %s 与 DESIGN.md 漂移："
                                   "DESIGN.md 写 %s，CSS 写 %s（以 DESIGN.md 为准）"
                                   % (var, prim_decl[var], value))
        else:                                    # semantic / component
            decl = sem if lyr == "semantic" else comp
            label = "语义变量（semantic）" if lyr == "semantic" else "组件变量（component）"
            if var not in decl:
                report.error("G7", "tokens.css 的 %s 是 %s 层变量，但 DESIGN.md 的「%s」"
                                   "段落没有声明它" % (var, "语义" if lyr == "semantic" else "组件", label))

    # 2) DESIGN.md 声明的每个变量：层要对得上，引用目标要不漂移
    for decl, want_layer, label in ((sem, "semantic", "语义变量（semantic）"),
                                    (comp, "component", "组件变量（component）")):
        for var, ref in sorted(decl.items()):
            if var not in css:
                report.warn("G7", "DESIGN.md 的「%s」声明了 %s，但 tokens.css 里没有（声明未落地）"
                                  % (label, var))
                continue
            if layers.get(var) != want_layer:
                report.error("G7", "DESIGN.md 把 %s 列为 %s 层，但 tokens.css 里它是 %s 层"
                                   "（取值 %s）——三层不许越级"
                                   % (var, want_layer, layers.get(var), css[var]))
                continue
            want, got = as_var(ref), ref_of(css[var])
            if got != want:
                report.error("G7", "tokens.css 的 %s 指向 %s，DESIGN.md 声明指向 %s（引用漂移）"
                                   % (var, got or css[var], want))

    # 3) G8：components-and-states.md「引用 token」列引用的 token 必须真实存在
    tokens_declared = set(css)
    title, body = find_component_table(doc_sections)
    if title is not None:
        rows = table_rows(body)
        header = rows[0] if rows else []
        col = {strip_ticks(h): i for i, h in enumerate(header)}
        i = col.get("引用 token", -1)
        if i < 0:
            report.warn("G8", "「%s」表头缺少「引用 token」列（无法校验 token 引用）" % title)
        else:
            for row in rows[1:]:
                if i >= len(row):
                    continue
                cid = strip_ticks(row[col.get("id", 0)]) if row else "?"
                for ref in re.findall(r"--jf-[a-z0-9-]*\*?", strip_ticks(row[i])):
                    if ref.endswith("*"):
                        # glob 是「族」声明：空命中给 WARN——模板里的 --jf-shell-* 就是占位，
                        # 拦住不让过会把模板本身判死；但空命中多半是族名改了，值得提示
                        if not any(v.startswith(ref[:-1]) for v in tokens_declared):
                            report.warn("G8", "组件 %s 的「引用 token」列写了 %s，"
                                              "tokens.css 里没有变量匹配（glob 空命中）"
                                              % (cid, ref))
                    elif ref not in tokens_declared:
                        # 具名 token 是「事实」声明：写了就必须存在
                        report.error("G8", "组件 %s 的「引用 token」列写了 %s，"
                                           "但 tokens.css 里没有这个变量" % (cid, ref))


# --------------------------------------------------------------------------- #
# 校验主逻辑
# --------------------------------------------------------------------------- #

def check_design(manifest: dict, root: str = ".") -> Report:
    """校验设计基线，root 为 manifest.design 路径的相对根目录。"""
    report = Report()

    if not isinstance(manifest, dict):
        report.error("G1", "manifest 顶层必须是对象")
        return report

    design = manifest.get("design")
    if not isinstance(design, dict):
        report.error("G1", "manifest 缺少 design 字段（Phase 2 起必填；"
                           "字段定义见 products/jiaofu/jf-contract/references/manifest-schema.md）")
        return report

    # ---------- DESIGN.md：G1 / G2 / G6 ----------
    spec_rel = design.get("spec")
    spec_text = None
    if not spec_rel:
        report.error("G1", "design.spec 未声明（DESIGN.md 路径）")
    else:
        spec_path = os.path.join(root, spec_rel)
        if not os.path.isfile(spec_path):
            report.error("G1", "DESIGN.md 不存在：%s" % spec_rel)
        else:
            with open(spec_path, encoding="utf-8") as f:
                spec_text = f.read()

    sections = split_sections(spec_text) if spec_text is not None else {}

    # G1：必含段落
    if spec_text is not None:
        for name, keywords in REQUIRED_SECTIONS:
            title, _ = find_section(sections, keywords)
            if title is None:
                report.error("G1", "DESIGN.md 缺少必含段落「%s」（标题需含关键词：%s）"
                             % (name, "/".join(keywords)))

        # G2：三层结构完整（三段都在且各有至少一行表数据）
        for layer, keywords in (("primitive", PRIMITIVE_KEYWORDS),
                                ("semantic", SEMANTIC_KEYWORDS),
                                ("component", COMPONENT_VAR_KEYWORDS)):
            title, body = find_section(sections, keywords)
            if title is None:
                continue  # 段落缺失已由 G1 报过
            if not table_rows(body):
                report.error("G2", "DESIGN.md 的 %s 层段落「%s」没有表数据（三层结构不完整）"
                             % (layer, title))

        # G2：semantic / component 层禁裸 hex
        for layer, keywords in (("semantic", SEMANTIC_KEYWORDS),
                                ("component", COMPONENT_VAR_KEYWORDS)):
            title, body = find_section(sections, keywords)
            if title is None:
                continue
            text = "\n".join(body)
            hits = HEX_RE.findall(text)
            if hits:
                report.error("G2", "DESIGN.md 的 %s 层段落「%s」出现裸值 hex：%s"
                             "（semantic/component 只能引用上一层，裸值只许在 primitive）"
                             % (layer, title, "、".join("#" + h for h in hits)))

        # G6：排除项明确（≥2 条非琐碎列表项，且提及字体/配色套路）
        title, body = find_section(sections, ("排除",))
        if title is not None:
            items = [ln.lstrip("-* ").strip() for ln in body
                     if ln.strip().startswith(("-", "* "))]
            items = [i for i in items if len(i) >= 6]
            if len(items) < 2:
                report.error("G6", "DESIGN.md 的「%s」不够明确：至少 2 条具体排除项"
                             "（当前 %d 条）" % (title, len(items)))
            elif not any(k in "\n".join(items) for k in
                         ("Inter", "Roboto", "Arial", "Grotesk", "字体", "灰字", "纯黑", "彩底")):
                report.error("G6", "DESIGN.md 的「%s」未写明禁用的字体/配色套路"
                             "（至少提及一类，如禁用 Inter/Roboto/Arial）" % title)

    # ---------- components-and-states.md：G3 / G4 / G5 ----------
    states_rel = design.get("states")
    states_text = None
    if not states_rel:
        report.error("G1", "design.states 未声明（components-and-states.md 路径）")
    else:
        states_path = os.path.join(root, states_rel)
        if not os.path.isfile(states_path):
            report.error("G1", "components-and-states.md 不存在：%s" % states_rel)
        else:
            with open(states_path, encoding="utf-8") as f:
                states_text = f.read()

    doc_sections = split_sections(states_text) if states_text is not None else {}
    comp_rows: list[list[str]] = []
    idx: dict[str, int] = {}
    cross_state_ids: set[str] = set()
    if states_text is not None:
        # 组件×状态表：表头须含 id + 四态列
        title, body = find_component_table(doc_sections)
        if title is None:
            report.error("G3", "components-and-states.md 缺少「组件×状态」表"
                             "（段落标题需含「组件」）")
        else:
            rows = table_rows(body)
            header, data = (rows[0], rows[1:]) if rows else ([], [])
            col = {strip_ticks(h): i for i, h in enumerate(header)}
            idx = {s: col.get(s, -1) for s in ("id", "类型") + COMPONENT_STATES}
            if idx["id"] < 0:
                report.error("G3", "「%s」表头缺少 id 列（组件须可追溯到 manifest）" % title)
            else:
                comp_rows = data
                if not data:
                    report.error("G3", "「%s」没有组件行" % title)

        # 跨模块状态表（排除「组件×状态」表，标题含「状态」即算）
        title, body = find_section(doc_sections, ("跨模块", "状态"), exclude=("组件",))
        if title is None:
            report.error("G4", "components-and-states.md 缺少「跨模块状态」表"
                             "（段落标题需含「跨模块」或「状态」）")
        else:
            rows = table_rows(body)
            cross_state_ids = {strip_ticks(r[0]) for r in rows[1:] if r}

        # G3：交互组件四态全 ✓；容器组件四态可标 —，但必须配落点说明
        notes = container_notes(doc_sections)
        for row in comp_rows:
            if idx["id"] >= len(row):
                continue
            cid = strip_ticks(row[idx["id"]]) if idx["id"] < len(row) else ""
            cname = row[0] if row else cid
            i_kind = idx.get("类型", -1)
            kind = strip_ticks(row[i_kind]) if 0 <= i_kind < len(row) else ""
            if kind and kind not in COMPONENT_KINDS:
                report.error("G3", "组件 %s（%s）的「类型」列取值「%s」非法（只能是 交互 / 容器）"
                             % (cid or "?", cname, kind))
            if kind == "容器":
                if cid not in notes:
                    report.error("G3", "组件 %s（%s）是容器，但表下缺少以「- `%s`：」开头的"
                                       "落点说明（容器可用 — 代替 ✓，代价是必须写清状态落在哪个子部件上）"
                                 % (cid or "?", cname, cid or "?"))
                continue
            for s in COMPONENT_STATES:
                i = idx[s]
                cell = row[i] if 0 <= i < len(row) else ""
                if not cell_marked(cell):
                    report.error("G3", "组件 %s（%s）的 %s 态未定义"
                                 "（交互组件四态 default/hover/active/disabled 必须全 ✓；"
                                 "容器组件请把「类型」列标为 容器 并补落点说明）"
                                 % (cid or "?", cname, s))

        # G4：五状态全部定义
        for s in CROSS_STATES:
            if s not in cross_state_ids:
                report.error("G4", "跨模块状态 %s 未定义（五状态 empty/loading/error/"
                                   "disabled/permission-denied 必须全部定义）" % s)

    # G5：组件能追溯到 manifest.components[].id
    manifest_ids = [c.get("id") for c in manifest.get("components") or []
                    if isinstance(c, dict) and c.get("id")]
    if states_text is not None and comp_rows and idx.get("id", -1) >= 0:
        doc_ids = [strip_ticks(r[idx["id"]]) for r in comp_rows
                   if idx["id"] < len(r) and strip_ticks(r[idx["id"]])]
        for did in doc_ids:
            if did not in manifest_ids:
                report.error("G5", "组件 %s 在 components-and-states.md 中声明，"
                                   "但 manifest.components[] 里没有该 id" % did)
        for mid in manifest_ids:
            if mid not in doc_ids:
                report.warn("G5", "manifest 组件 %s 未出现在 components-and-states.md"
                                  "（设计基线未覆盖全部组件）" % mid)

    # G7 / G8：三层落地一致性与 token 引用可解析（需要 spec + states 都读到）
    check_token_landing(report, design, root, sections, doc_sections)

    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def render_text(report: Report, manifest_path: str) -> str:
    lines = []
    lines.append("校验对象：%s（设计基线 G1–G8）" % manifest_path)
    lines.append("")
    if not report.issues:
        lines.append("✅ 全部通过，无问题。")
        return "\n".join(lines)
    if report.errors:
        lines.append("❌ 错误 %d 条：" % len(report.errors))
        lines.extend(str(i) for i in report.errors)
        lines.append("")
    if report.warnings:
        lines.append("⚠️  警告 %d 条：" % len(report.warnings))
        lines.extend(str(i) for i in report.warnings)
        lines.append("")
    if not report.errors:
        lines.append("✅ 无错误；但有 %d 条警告。" % len(report.warnings))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 自检样例
# --------------------------------------------------------------------------- #

_VALID_DESIGN_MD = """# DESIGN.md — 自检合法样例

## 产品基调

面向企业内部管理员的专业工具，克制、信息密度优先。

## 色板（primitive）

| token | 值 | 用途 |
|---|---|---|
| `blue-600` | `#2563eb` | 主操作 |
| `gray-900` | `#1f2328` | 主文本 |

## 字体与字阶

| token | 值 | 用途 |
|---|---|---|
| `font-ui` | `-apple-system, sans-serif` | 界面字体 |

## 间距 / 圆角 / 阴影栅格

| token | 值 | 用途 |
|---|---|---|
| `space-4` | `16px` | 常规内边距 |

## 语义变量（semantic）

| 变量 | 引用 | 用途 |
|---|---|---|
| `--jf-accent` | `blue-600` | 主强调色 |
| `--jf-text` | `gray-900` | 主文本 |

## 组件变量（component）

| 变量 | 引用 | 用途 |
|---|---|---|
| `--jf-btn-bg` | `--jf-accent` | 主按钮底色 |

## 明确排除项

- 禁用字体 Inter / Roboto / Arial（被 AI 用烂）
- 禁灰字配彩底，对比度不足
"""

_INVALID_DESIGN_MD = """# DESIGN.md — 自检非法样例

## 色板（primitive）

| token | 值 | 用途 |
|---|---|---|
| `blue-600` | `#2563eb` | 主操作 |

## 字体与字阶

| token | 值 | 用途 |
|---|---|---|
| `font-ui` | `-apple-system, sans-serif` | 界面字体 |

## 间距 / 圆角 / 阴影栅格

| token | 值 | 用途 |
|---|---|---|
| `space-4` | `16px` | 常规内边距 |

## 语义变量（semantic）

| 变量 | 引用 | 用途 |
|---|---|---|
| `--jf-accent` | `#2563eb` | 裸值打回 |

## 组件变量（component）

（空——三层不完整）

## 明确排除项

- 少一条
"""

_VALID_STATES_MD = """# components-and-states.md — 自检合法样例

## 组件×状态

| 组件 | id | 类型 | default | hover | active | disabled | 其他状态 | 引用 token | usedBy |
|---|---|---|---|---|---|---|---|---|---|
| 页面外壳 | `page-shell` | 交互 | ✓ | ✓ | ✓ | ✓ | — | `--jf-accent`、`--jf-text` | demand-list |
| 数据表格 | `data-table` | 交互 | ✓ | ✓ | ✓ | ✓ | loading/empty | `--jf-btn-*` | demand-list |

## 跨模块状态

| 状态 | 触发场景 | 视觉表现 | 文案口径 | 落点组件 |
|---|---|---|---|---|
| `empty` | 无数据 | 居中空态 | 暂无数据 | `data-table` |
| `loading` | 加载中 | 骨架屏 | — | `data-table` |
| `error` | 请求失败 | 错误条 | 请重试 | `data-table` |
| `disabled` | 无权限 | 降透明度 | — | `page-shell` |
| `permission-denied` | 无页面权限 | 无权限卡 | 联系管理员 | `page-shell` |
"""

_INVALID_STATES_MD = """# components-and-states.md — 自检非法样例

## 组件×状态

| 组件 | id | default | hover | active | disabled | 其他状态 | 引用 token | usedBy |
|---|---|---|---|---|---|---|---|---|
| 页面外壳 | `page-shell` | ✓ | ✓ | ✓ | ✓ | — | `--jf-shell-*` | demand-list |
| 数据表格 | `data-table` | ✓ | — | ✓ | ✓ | loading | `--jf-table-*`、`--jf-nope` | demand-list |
| 幽灵按钮 | `ghost-button` | ✓ | ✓ | ✓ | ✓ | — | `--jf-btn-*` | demand-list |

## 跨模块状态

| 状态 | 触发场景 | 视觉表现 | 文案口径 | 落点组件 |
|---|---|---|---|---|
| `empty` | 无数据 | 居中空态 | 暂无数据 | `data-table` |
| `loading` | 加载中 | 骨架屏 | — | `data-table` |
| `error` | 请求失败 | 错误条 | 请重试 | `data-table` |
| `disabled` | 无权限 | 降透明度 | — | `page-shell` |
"""


_TEMPLATE_SHAPED_STATES_MD = """# components-and-states.md — 示例产品 组件×状态契约

> 按 design-contract.md 模板写：H1 标题本身含「组件」二字，且标题下方没有表。

## 组件×状态

| 组件 | id | default | hover | active | disabled | 其他状态 | 引用 token | usedBy |
|---|---|---|---|---|---|---|---|---|
| 页面外壳 | `page-shell` | ✓ | ✓ | ✓ | ✓ | — | `--jf-shell-*` | demand-list |
| 数据表格 | `data-table` | ✓ | ✓ | ✓ | ✓ | loading/empty | `--jf-table-*` | demand-list |

## 跨模块状态

| 状态 | 触发场景 | 视觉表现 | 文案口径 | 落点组件 |
|---|---|---|---|---|
| `empty` | 无数据 | 居中空态 | 暂无数据 | `data-table` |
| `loading` | 加载中 | 骨架屏 | — | `data-table` |
| `error` | 请求失败 | 错误条 | 请重试 | `data-table` |
| `disabled` | 无权限 | 降透明度 | — | `page-shell` |
| `permission-denied` | 无页面权限 | 无权限卡 | 联系管理员 | `page-shell` |
"""


_VALID_TOKENS_CSS = """/* 自检合法样例：与 _VALID_DESIGN_MD 一一对应 */
:root {
  --jf-blue-600: #2563eb;
  --jf-gray-900: #1f2328;
  --jf-font-ui: -apple-system, sans-serif;
  --jf-space-4: 16px;
}
:root {
  --jf-accent: var(--jf-blue-600);
  --jf-text: var(--jf-gray-900);
}
:root {
  --jf-btn-bg: var(--jf-accent);
}
"""

# 三类漂移各一：未声明的裸值 / 引用指向漂移 / 越级（component 直接引用 primitive）
_DRIFT_TOKENS_CSS = """/* 自检漂移样例：DESIGN.md ↔ tokens.css 三处不一致 */
:root {
  --jf-blue-600: #2563eb;
  --jf-gray-900: #1f2328;
  --jf-font-ui: -apple-system, sans-serif;
  --jf-space-4: 16px;
  --jf-red-600: #dc2626;
}
:root {
  --jf-accent: var(--jf-red-600);
}
:root {
  --jf-btn-bg: var(--jf-blue-600);
}
"""

# 容器组件样例：page-shell 标 容器，四态可 —，但必须配落点说明
_CONTAINER_STATES_MD = """# components-and-states.md — 容器样例

## 组件×状态

| 组件 | id | 类型 | default | hover | active | disabled | 其他状态 | 引用 token | usedBy |
|---|---|---|---|---|---|---|---|---|---|
| 页面外壳 | `page-shell` | 容器 | ✓ | — | — | — | — | `--jf-accent` | demand-list |
| 数据表格 | `data-table` | 交互 | ✓ | ✓ | ✓ | ✓ | loading/empty | `--jf-btn-*` | demand-list |

容器类组件的四态落点写在这里：

- `page-shell`：hover 落在左侧导航项；active 落在当前导航项高亮；disabled 落在无权限时的导航项灰化。

## 跨模块状态

| 状态 | 触发场景 | 视觉表现 | 文案口径 | 落点组件 |
|---|---|---|---|---|
| `empty` | 无数据 | 居中空态 | 暂无数据 | `data-table` |
| `loading` | 加载中 | 骨架屏 | — | `data-table` |
| `error` | 请求失败 | 错误条 | 请重试 | `data-table` |
| `disabled` | 无权限 | 降透明度 | — | `page-shell` |
| `permission-denied` | 无页面权限 | 无权限卡 | 联系管理员 | `page-shell` |
"""

# 同上但抽掉落点说明：容器标了 — 却没说状态落在哪，G3 必须报出
_CONTAINER_NO_NOTE_STATES_MD = _CONTAINER_STATES_MD.replace(
    """
容器类组件的四态落点写在这里：

- `page-shell`：hover 落在左侧导航项；active 落在当前导航项高亮；disabled 落在无权限时的导航项灰化。
""", "")


def _sample_manifest():
    return {
        "schemaVersion": 1,
        "product": {"name": "XX系统", "type": "Web"},
        "design": {"spec": "DESIGN.md", "states": "components-and-states.md",
                   "tokens": "prototypes/shared/tokens.css"},
        "components": [
            {"id": "page-shell", "title": "页面外壳", "usedBy": ["demand-list"]},
            {"id": "data-table", "title": "数据表格", "usedBy": ["demand-list"]},
        ],
    }


def self_test() -> int:
    print("=== check_design.py 自检 ===")
    ok = True

    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "prototypes/shared"), exist_ok=True)
        tokens_path = os.path.join(td, "prototypes/shared/tokens.css")

        # 1) 合法样例：期望 0 error（含 G7/G8 —— tokens.css 与 DESIGN.md 一致）
        with open(os.path.join(td, "DESIGN.md"), "w", encoding="utf-8") as f:
            f.write(_VALID_DESIGN_MD)
        with open(os.path.join(td, "components-and-states.md"), "w", encoding="utf-8") as f:
            f.write(_VALID_STATES_MD)
        with open(tokens_path, "w", encoding="utf-8") as f:
            f.write(_VALID_TOKENS_CSS)
        rep = check_design(_sample_manifest(), root=td)
        if rep.errors:
            ok = False
            print("❌ 合法样例应无 ERROR，实际 %d 条：" % len(rep.errors))
            for i in rep.errors:
                print(i)
        else:
            print("✅ 合法样例：0 error（警告 %d 条）" % len(rep.warnings))

        # 2) 非法样例：期望逐条报出 G1–G8
        with open(os.path.join(td, "DESIGN.md"), "w", encoding="utf-8") as f:
            f.write(_INVALID_DESIGN_MD)
        with open(os.path.join(td, "components-and-states.md"), "w", encoding="utf-8") as f:
            f.write(_INVALID_STATES_MD)
        with open(tokens_path, "w", encoding="utf-8") as f:
            f.write(_DRIFT_TOKENS_CSS)
        rep2 = check_design(_sample_manifest(), root=td)
        codes = {i.code for i in rep2.errors}
        expected = {"G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"}
        missing = expected - codes
        if missing:
            ok = False
            print("❌ 非法样例未报出的门禁码：%s" % ", ".join(sorted(missing)))
        else:
            print("✅ 非法样例：G1–G8 全部命中（共 %d 条错误）" % len(rep2.errors))

        # 2b) G7 三处漂移都要抓得住：未声明的裸值 / 引用漂移 / 越级
        drift_msgs = "\n".join(i.message for i in rep2.errors if i.code == "G7")
        for kw, what in (("--jf-red-600", "未声明的裸值"),
                         ("引用漂移", "引用指向漂移")):
            if kw not in drift_msgs:
                ok = False
                print("❌ G7 未报出「%s」" % what)
        if "未声明的裸值" in drift_msgs and "引用漂移" in drift_msgs:
            print("✅ G7 抓到漂移（未声明的裸值 + 引用指向漂移）")

        # 2c) 容器组件：可标 —，但落点说明不能少
        with open(os.path.join(td, "DESIGN.md"), "w", encoding="utf-8") as f:
            f.write(_VALID_DESIGN_MD)
        with open(os.path.join(td, "components-and-states.md"), "w", encoding="utf-8") as f:
            f.write(_CONTAINER_STATES_MD)
        with open(tokens_path, "w", encoding="utf-8") as f:
            f.write(_VALID_TOKENS_CSS)
        rep_c = check_design(_sample_manifest(), root=td)
        if rep_c.errors:
            ok = False
            print("❌ 容器标 — 且配了落点说明：应无 ERROR，实际 %d 条：" % len(rep_c.errors))
            for i in rep_c.errors:
                print(i)
        else:
            print("✅ 容器组件：标 — 且配落点说明即通过")
        with open(os.path.join(td, "components-and-states.md"), "w", encoding="utf-8") as f:
            f.write(_CONTAINER_NO_NOTE_STATES_MD)
        rep_c2 = check_design(_sample_manifest(), root=td)
        if any(i.code == "G3" and "落点说明" in i.message for i in rep_c2.errors):
            print("✅ 容器组件：标 — 却缺落点说明 → G3 报出")
        else:
            ok = False
            print("❌ 容器标 — 缺落点说明应报 G3")
        # 交互组件标 — 仍必须报出（类型列不是免死金牌）
        with open(os.path.join(td, "components-and-states.md"), "w", encoding="utf-8") as f:
            f.write(_CONTAINER_NO_NOTE_STATES_MD.replace(
                "| 数据表格 | `data-table` | 交互 | ✓ | ✓ | ✓ | ✓ |",
                "| 数据表格 | `data-table` | 交互 | ✓ | — | ✓ | ✓ |"))
        rep_c3 = check_design(_sample_manifest(), root=td)
        if any(i.code == "G3" and "data-table" in i.message for i in rep_c3.errors):
            print("✅ 交互组件：标 — → G3 照常报出")
        else:
            ok = False
            print("❌ 交互组件标 — 应报 G3")

        # 3) design 字段缺失：G1 报错且不崩
        m = _sample_manifest()
        del m["design"]
        rep3 = check_design(m, root=td)
        if rep3.errors and rep3.errors[0].code == "G1":
            print("✅ 缺 design 字段：G1 报错（%s）" % rep3.errors[0].message[:30] + "…")
        else:
            ok = False
            print("❌ 缺 design 字段应报 G1")

        # 4) 模板形状的 H1（标题含「组件」但正文无表）：不得误判为「表头缺 id 列」
        with open(os.path.join(td, "DESIGN.md"), "w", encoding="utf-8") as f:
            f.write(_VALID_DESIGN_MD)  # 第 2 步换成了非法样例，这里换回来
        with open(os.path.join(td, "components-and-states.md"), "w", encoding="utf-8") as f:
            f.write(_TEMPLATE_SHAPED_STATES_MD)
        rep4 = check_design(_sample_manifest(), root=td)
        if rep4.errors:
            ok = False
            print("❌ 模板形状样例应无 ERROR，实际 %d 条：" % len(rep4.errors))
            for i in rep4.errors:
                print(i)
        else:
            print("✅ 模板形状 H1：正确落到「组件×状态」表（0 error）")

        # 5) 「组件」段落有表但确实缺 id 列：仍须报 G3
        with open(os.path.join(td, "components-and-states.md"), "w", encoding="utf-8") as f:
            f.write(_TEMPLATE_SHAPED_STATES_MD.replace("| 组件 | id |", "| 组件 | 编号 |"))
        rep5 = check_design(_sample_manifest(), root=td)
        if any(i.code == "G3" and "id 列" in i.message for i in rep5.errors):
            print("✅ 真缺 id 列：G3 照常报出")
        else:
            ok = False
            print("❌ 缺 id 列应报 G3「表头缺少 id 列」")

    print("=== 自检%s ===" % ("通过" if ok else "失败"))
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="校验 jf-design 设计基线契约（G1–G8）")
    parser.add_argument("manifest", nargs="?", help="manifest.json 路径")
    parser.add_argument("--root", default=None,
                        help="design 路径字段的相对根目录，默认 manifest 所在目录")
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
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError) as e:
        print("manifest 解析失败：%s" % e, file=sys.stderr)
        return 2

    root = args.root or os.path.dirname(path)
    report = check_design(manifest, root=root)

    if args.as_json:
        print(json.dumps({
            "manifest": path,
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
