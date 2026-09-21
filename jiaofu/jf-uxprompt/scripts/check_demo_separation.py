#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_demo_separation.py — 客户演示档的「双层分离」门禁（A1–A6 / B1–B2）

演示档是**两棵树**里给客户看的那棵（`render_manifest.py --demo`），要跟设计评审
那棵物理分开：PM 的注释、编号、页 ID 留在评审树，客户树里只有业务语言。
本脚本是这条纪律的机器检查——纪律原文见 `products/jiaofu/jf-uxprompt/SKILL.md`
「演示档纪律」。

用法：
  python3 check_demo_separation.py <演示根目录> [--manifest <manifest.json>]
                                   [--notes <设计注释.md>] [--json]

  <演示根目录>  --demo 渲染出来的那棵树（含 console.html 与 pages/）
  --manifest    取 scenes[] 做 B 侧交叉校验；缺省在演示根目录下找 manifest.json
  --notes       产物B（jf-review 产出的设计注释文档）。**不给就只跑 A 侧**——
                B 由另一个 skill 产出，跨 skill 调用时本脚本不该假装它存在。
  --json        机器可读输出

校验规则：

  A 侧（演示树，永远跑）——**扫 *.html 的原始文本，含注释**：
    A1  演示目录存在且至少有 1 张 HTML
    A2  零 PM 关键词（FR-/AC-/BR-/SM-/UC- 编号、规则来源、页面ID、MRD/PRD…）
    A3  零标注层残留（jf-ann-badge / jf-ann-panel / jf-ann-all / jf-meta /
        jf-bubble / JF-ANNOTATION-SECTION）
    A4  PM 展示页不存在（index.html / components.html / states.html 三张不得与
        console.html 同处一层）
    A5  console.html 存在（演示树的入口）
    A6  页 ID 不得作为**可见文本**出现（给了 manifest 才跑）

  B 侧（产物B，仅 --notes）：
    B1  产物B 存在、非空、是 .md
    B2  manifest.scenes[] 每项的 id / title / source 都出现在产物B 里

A6 为什么单独一条：词表里的「页面ID」是那三个字，不是页 ID 本身——`demand-list`
这种真 ID 从词表下溜得过去。而页 ID 在演示树里**并非一律禁止**：跳转协议的
`href="pages/demand-list.html"` 与 `data-nav="demand-list"` 必须留着（脱离工具
也能跳是底线）。所以判据落在「**可见文本**」上：剥掉标签、脚本、样式之后，
页 ID 不该出现在客户读得到的字里。attributes 里的 ID 不进这个判据。

A4 为什么查「console.html 的同层」而不是全树同名文件：本套件的落点是**构造性**的
——`render_manifest.py` 把这三张页写在 `console.html` 同一层，所以那儿有就是泄漏。
按 basename 全树扫会误伤**产品自己的** `index.html`（真实项目里到处都是）。
⚠️ 外部执行者把 `console.html` 放到别处时，这条判据要跟着它的落点重定。

退出码：0 通过（WARN 仍算通过）/ 1 不通过（存在 ERROR）/ 2 用法错误

--- 为什么 A2/A3 只扫 .html，不扫 shared/*.js|css ---

「正文层」= 客户打开就能读到的那一层，也就是 .html。`shared/` 是**运行时**：
两棵树逐字节相同、只讲代码不讲业务，它的注释里出现「标注气泡」是描述实现，
不是 PM 内容——拿词表去扫它只会得到一个假阳性，还会逼着评审树的运行时刻意换词。
**这不是给「把 PM 词藏进 JS 字符串」留口子**：本套件的演示树产物由
`render_manifest.py --demo` 生成，`shared/` 里没有任何 manifest 内容进得去；
换了外部执行者、由它自己写 `shared/` 时，这条边界要重新审。

--- 词表里两个会误伤的词 ---

`注释` 与 `标注` 是业务上可能正当出现的词（例：一个讲文档批注的产品）。
本脚本照合并前 jf-hifi（未发布，已并入本套件）的原表一并判 ERROR，不设分级——演示档的内容由 manifest 与
渲染器定，我们自己产出跑得过；真出现业务正当命中时，人来看一眼这条 ERROR、
决定是改词还是改门禁，比门禁自己猜要诚实。报错会带文件名与行号，一眼可判。
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

# 演示树里禁止出现的 PM 注释关键词（沿用上面那张原表：那份表是对的，
# 出问题的是它**先剥注释再查**——隐藏注释正是它 SKILL.md 禁止的那件事）。
FORBIDDEN = (
    "设计注释", "内部注释", "交互标注", "设计说明", "客户适配",
    "页面ID", "产品经理", "拆解", "MRD", "PRD", "规则来源",
    "内部评审", "内部备注", "仅内部", "注释", "标注",
    "FR-", "AC-", "BR-", "SM-", "UC-",
)

# 标注层机件：出现在演示页里就说明「摘 chrome」漏了（含 HTML 注释里的残留）。
ANN_MARKERS = (
    "jf-ann-badge", "jf-ann-panel", "jf-ann-all",
    "class=\"jf-meta\"", "jf-bubble", "JF-ANNOTATION-SECTION",
)

# PM 专用的三张展示页：与 console.html 同层出现即为泄漏。
# 它们写着「原型索引 / 只列导航页（standalone） / 设计基线 / 组件 × 状态」，
# 还逐个列出页 ID——全是工程视角，客户不该拿到。
PM_PAGES = ("index.html", "components.html", "states.html")

CONSOLE = "console.html"


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
# A 侧：演示树
# --------------------------------------------------------------------------- #

def html_files(root: str) -> list:
    """演示树下的全部 *.html，路径排序保证输出稳定。"""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.lower().endswith((".html", ".htm")):
                found.append(os.path.join(dirpath, fn))
    return sorted(found)


def hit_lines(text: str, term: str) -> list:
    """term 命中的行号（1 起）。带行号，命中是真是假一眼可判。"""
    return [n for n, line in enumerate(text.splitlines(), 1) if term in line]


# 内联脚本/样式整块（连同内容）与其余标签。剥掉它们剩下的才是「可见文本」——
# 属性里的 href / data-nav 随标签一起去掉，正是我们要的：页 ID 允许留在
# 跳转协议里，不允许出现在客户读得到的字里。
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def visible_text(html_text: str) -> str:
    return _TAG_RE.sub(" ", _SCRIPT_STYLE_RE.sub(" ", html_text))


def id_occurrences(plain: str, pid: str) -> list:
    """页 ID 在可见文本里的命中行号。要求两侧不是 kebab 字符，
    免得 `list` 这种短 ID 在英文散文里误伤。"""
    pat = re.compile(r"(?<![A-Za-z0-9-])%s(?![A-Za-z0-9-])" % re.escape(pid))
    return [n for n, line in enumerate(plain.splitlines(), 1) if pat.search(line)]


def check_demo_tree(root: str, report: Report, page_ids=None) -> None:
    if not os.path.isdir(root):
        report.error("A1", "演示目录不存在：%s" % root)
        return

    pages = html_files(root)
    if not pages:
        report.error("A1", "演示目录里一张 HTML 都没有：%s" % root)
        return

    # A2 / A3 / A6：原始文本（含注释）——客户按 Ctrl+U 就能看到，藏注释等于没摘
    for path in pages:
        rel = os.path.relpath(path, root)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            report.error("A1", "读不了 %s：%s" % (rel, e))
            continue
        for term in FORBIDDEN:
            lines = hit_lines(text, term)
            if lines:
                report.error("A2", "%s 命中 PM 关键词「%s」（第 %s 行）——"
                                   "演示树是给客户看的，Ctrl+U 也看得见"
                                   % (rel, term, ",".join(str(n) for n in lines[:5])))
        for mark in ANN_MARKERS:
            lines = hit_lines(text, mark)
            if lines:
                report.error("A3", "%s 残留标注层机件「%s」（第 %s 行）——"
                                   "--demo 应当是整层不渲染，不是隐藏"
                                   % (rel, mark, ",".join(str(n) for n in lines[:5])))
        if page_ids:
            plain = visible_text(text)
            for pid in page_ids:
                lines = id_occurrences(plain, pid)
                if lines:
                    report.error("A6", "%s 把页 ID「%s」当正文露出来了（第 %s 行）"
                                       "——ID 留在 href/data-nav 里没问题，"
                                       "写成客户读得到的字就是工程标注"
                                       % (rel, pid, ",".join(str(n) for n in lines[:5])))

    # A5：console.html 是演示树的入口，先定位它
    console = None
    for path in pages:
        if os.path.basename(path) == CONSOLE:
            console = path
            break
    if console is None:
        report.error("A5", "演示树里没有 %s——它是演示档的入口页，"
                           "没有它这棵树无从进起" % CONSOLE)
        return

    # A4：PM 展示页不得与 console.html 同层（渲染器的落点就在这一层）
    console_dir = os.path.dirname(console)
    for name in PM_PAGES:
        stray = os.path.join(console_dir, name)
        if os.path.isfile(stray):
            report.error("A4", "%s 与 %s 同层——这张是 PM 专用展示页"
                               "（原型索引 / 设计基线 / 组件×状态），"
                               "演示档应当不产出它，而不是留在目录里"
                               % (name, CONSOLE))


def load_page_ids(manifest_path, report: Report) -> list:
    """从 manifest 取页 ID 供 A6 用。没有 manifest 就 WARN 跳过——
    A 侧是主线，不该因为旁证缺席就判失败。"""
    if not manifest_path or not os.path.isfile(manifest_path):
        report.warn("A6", "没有 manifest，跳过「页 ID 是否露成正文」检查"
                          "（给 --manifest，或在演示根目录下放一份 manifest.json）")
        return []
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError) as e:
        report.warn("A6", "manifest 解析失败，跳过 A6：%s" % e)
        return []
    return [p["id"] for p in manifest.get("pages", [])
            if isinstance(p, dict) and p.get("id")]


# --------------------------------------------------------------------------- #
# B 侧：产物B（设计注释文档，jf-review 产出）
# --------------------------------------------------------------------------- #

def check_notes(notes_path: str, manifest_path, report: Report) -> None:
    if not notes_path:
        return
    if not os.path.isfile(notes_path):
        report.error("B1", "产物B 不存在：%s" % notes_path)
        return
    if not notes_path.lower().endswith(".md"):
        report.error("B1", "产物B 不是 Markdown：%s" % notes_path)
    try:
        with open(notes_path, encoding="utf-8") as f:
            notes = f.read()
    except (OSError, UnicodeDecodeError) as e:
        report.error("B1", "读不了产物B：%s" % e)
        return
    if not notes.strip():
        report.error("B1", "产物B 是空的：%s" % notes_path)
        return

    # B2 需要 manifest 的 scenes[]
    if not manifest_path:
        report.error("B2", "要做 B 侧交叉校验，得给 --manifest（或在演示根目录"
                           "下放一份 manifest.json）——没有 scenes[] 就无从对拍")
        return
    if not os.path.isfile(manifest_path):
        report.error("B2", "manifest 不存在：%s" % manifest_path)
        return
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError) as e:
        report.error("B2", "manifest 解析失败：%s" % e)
        return

    scenes = manifest.get("scenes") or []
    if not scenes:
        report.warn("B2", "manifest 未声明 scenes[]，B 侧无场景可交叉校验"
                          "（与套件「没配执行者就走内置路径」同款：不阻塞）")
        return

    # 交叉校验：每条场景的 id / title / source 都得在产物B 里露面。
    # 这是替代合并进来那套 `any(k in text for k in [一个词])` 的判断——
    # 那个近乎恒真，等于没查。id/title/source 全中才证明产物B 真的把
    # manifest 里的场景逐条落进了文档，而不是写了一堆通用模板话。
    missing = []
    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        for field in ("id", "title", "source"):
            val = sc.get(field)
            if val and val not in notes:
                missing.append("%s.%s（%s）" % (sc.get("id", "?"), field, val))
    if missing:
        report.error("B2", "产物B 缺了 %d 项场景追溯：%s"
                           % (len(missing), "；".join(missing[:6])
                              + ("…" if len(missing) > 6 else "")))


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #

def render_text(report: Report, root: str, notes_path, manifest_path) -> str:
    lines = ["校验对象：%s" % root]
    lines.append("B 侧产物：%s" % (notes_path or "（未给 --notes，只跑 A 侧）"))
    if notes_path:
        lines.append("场景来源：%s" % (manifest_path or "（未找到 manifest）"))
    lines.append("")
    if not report.issues:
        lines.append("✅ 双层分离通过：演示树零 PM 注释，产物B 完整。")
        return "\n".join(lines)
    if report.errors:
        lines.append("❌ 错误 %d 条（分离未通过，不许交付给客户）：" % len(report.errors))
        lines.extend(str(i) for i in report.errors)
        lines.append("")
    if report.warnings:
        lines.append("⚠️  警告 %d 条：" % len(report.warnings))
        lines.extend(str(i) for i in report.warnings)
        lines.append("")
    if not report.errors:
        lines.append("✅ 门禁通过%s。" % ("；但有 %d 条警告" % len(report.warnings)
                                     if report.warnings else ""))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 自检样例
# --------------------------------------------------------------------------- #

def _write(root: str, files: dict) -> None:
    for rel, content in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


_CLEAN_PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>需求列表</title></head><body>
<nav class="jf-nav"><a href="../index.html">需求管理</a></nav>
<button class="jf-state-btn" data-state="empty">空态</button>
<div class="jf-state-body" data-state-block="empty">还没有需求，点右上角新建。</div>
</body></html>
"""

_CLEAN_CONSOLE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>演示控制台</title></head><body>
<h2>需求管理</h2><ol><li><a href="pages/demand-list.html?state=empty">列表空态</a></li></ol>
</body></html>
"""

_CLEAN_NOTES = """# 设计注释（内部）

## 场景清单
- demand-first-empty · 首次进入还没有需求 · 来源 AC-05-1
"""


def _manifest() -> dict:
    return {"scenes": [{"id": "demand-first-empty", "moduleId": "demand",
                        "title": "首次进入还没有需求", "source": "AC-05-1",
                        "steps": [{"pageId": "demand-list", "state": "empty",
                                   "label": "列表空态"}]}]}


def self_test() -> int:
    print("=== check_demo_separation.py 自检 ===")
    ok = True

    def expect(name, fn, want_codes, want_clean=False):
        nonlocal ok
        rep = Report()
        fn(rep)
        codes = {i.code for i in rep.errors}
        if want_clean:
            if rep.errors:
                ok = False
                print("❌ %s：应当 0 error，实际 %s" % (name, sorted(codes)))
                for i in rep.errors:
                    print(i)
            else:
                print("✅ %s：0 error" % name)
        elif not want_codes <= codes:
            ok = False
            print("❌ %s：应命中 %s，实际 %s" % (name, sorted(want_codes), sorted(codes)))
        else:
            print("✅ %s：命中 %s" % (name, sorted(want_codes)))

    def tree(rep, root, pids=()):
        return check_demo_tree(root, rep, list(pids))

    with tempfile.TemporaryDirectory() as td:
        # 1) 干净样例：无 ERROR
        clean = os.path.join(td, "clean")
        _write(clean, {"prototypes/console.html": _CLEAN_CONSOLE,
                       "prototypes/pages/demand-list.html": _CLEAN_PAGE})
        expect("干净演示树", lambda r: tree(r, clean, ["demand-list"]),
               set(), want_clean=True)

        # 2) PM 词藏在 HTML 注释里——合并前的原脚本先剥注释，这条会漏
        dirty = os.path.join(td, "dirty")
        _write(dirty, {"prototypes/console.html": _CLEAN_CONSOLE,
                       "prototypes/pages/demand-list.html":
                           _CLEAN_PAGE.replace("<body>",
                                               "<body>\n<!-- 产品经理：此处按 PRD 的 FR-09 处理 -->")})
        expect("PM 词藏在注释里", lambda r: tree(r, dirty), {"A2"})

        # 3) 标注层残留
        ann = os.path.join(td, "ann")
        _write(ann, {"prototypes/console.html": _CLEAN_CONSOLE,
                     "prototypes/pages/demand-list.html":
                         _CLEAN_PAGE.replace("<body>",
                                             '<body><span class="jf-ann-badge">1</span>')})
        expect("标注层残留", lambda r: tree(r, ann), {"A3"})

        # 4) PM 展示页与 console 同层
        stray = os.path.join(td, "stray")
        _write(stray, {"prototypes/console.html": _CLEAN_CONSOLE,
                       "prototypes/pages/demand-list.html": _CLEAN_PAGE,
                       "prototypes/index.html": "<html>原型索引</html>"})
        expect("PM 展示页混入", lambda r: tree(r, stray), {"A4"})

        # 5) 没有 console.html
        nocon = os.path.join(td, "nocon")
        _write(nocon, {"prototypes/pages/demand-list.html": _CLEAN_PAGE})
        expect("缺 console.html", lambda r: tree(r, nocon), {"A5"})

        # 6) 空目录
        empty = os.path.join(td, "empty")
        os.makedirs(empty)
        expect("空目录", lambda r: tree(r, empty), {"A1"})

        # 7) A6 正向：页 ID 写成正文
        leaked = os.path.join(td, "leaked")
        _write(leaked, {"prototypes/console.html": _CLEAN_CONSOLE,
                        "prototypes/pages/demand-list.html":
                            _CLEAN_PAGE.replace("还没有需求，点右上角新建。",
                                                "demand-list 还没有需求，点右上角新建。")})
        expect("页 ID 露成正文", lambda r: tree(r, leaked, ["demand-list"]), {"A6"})

        # 8) A6 反向：ID 只出现在 href / data-nav 里，不算露
        #    （跳转协议必须留着 ID——这条防的是「把 A6 写成见到 ID 就报」）
        inattr = os.path.join(td, "inattr")
        _write(inattr, {"prototypes/console.html":
                            _CLEAN_CONSOLE.replace("pages/demand-list.html",
                                                   "pages/demand-list.html"),
                        "prototypes/pages/demand-list.html":
                            '<html><body><a href="../pages/demand-list.html" '
                            'data-nav="demand-list">需求列表</a></body></html>'})
        expect("ID 只在 href/data-nav 里", lambda r: tree(r, inattr, ["demand-list"]),
               set(), want_clean=True)

        # 9) A6 子串边界：短 ID 不该在更长的 kebab 词里误伤
        substr = os.path.join(td, "substr")
        _write(substr, {"prototypes/console.html": _CLEAN_CONSOLE,
                        "prototypes/pages/demand-list.html":
                            _CLEAN_PAGE.replace("还没有需求，点右上角新建。",
                                                "这个 demand-list-x 不是页 ID。")})
        expect("短 ID 子串不误伤", lambda r: tree(r, substr, ["demand-list"]),
               set(), want_clean=True)

        # 10) B 侧：产物B 缺 source
        mpath = os.path.join(td, "manifest.json")
        _write(td, {"manifest.json": json.dumps(_manifest(), ensure_ascii=False)})
        partial = os.path.join(td, "partial.md")
        _write(td, {"partial.md": "# 设计注释\n\n- demand-first-empty · 首次进入还没有需求\n"})
        expect("产物B 缺 source",
               lambda r: check_notes(partial, mpath, r), {"B2"})

        # 11) B 侧：产物B 完整
        full = os.path.join(td, "full.md")
        _write(td, {"full.md": _CLEAN_NOTES})
        expect("产物B 完整",
               lambda r: check_notes(full, mpath, r), set(), want_clean=True)

        # 12) B 侧：给了 --notes 却没有 manifest
        expect("产物B 无 manifest",
               lambda r: check_notes(full, None, r), {"B2"})

    print()
    print("自检%s" % ("通过 ✅" if ok else "未通过 ❌"))
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="客户演示档双层分离门禁：演示树零 PM 注释 + 产物B 场景追溯齐全")
    ap.add_argument("demo_root", nargs="?", help="--demo 渲染出的演示树根目录")
    ap.add_argument("--manifest", default=None,
                    help="manifest.json 路径（B 侧交叉校验用 scenes[]；"
                         "缺省在演示根目录下找 manifest.json）")
    ap.add_argument("--notes", default=None,
                    help="产物B（设计注释文档 .md）。不给则只跑 A 侧")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="机器可读输出")
    ap.add_argument("--self-test", action="store_true",
                    help="用内置合法/非法样例验证脚本本身")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.demo_root:
        ap.print_help(sys.stderr)
        return 2

    root = os.path.abspath(args.demo_root)

    # manifest 先定：A6 要用页 ID，B 侧要用 scenes[]，两边共用一次发现逻辑
    manifest_path = args.manifest
    if not manifest_path:
        guess = os.path.join(root, "manifest.json")
        manifest_path = guess if os.path.isfile(guess) else None

    report = Report()
    check_demo_tree(root, report, load_page_ids(manifest_path, report))
    if args.notes:
        check_notes(os.path.abspath(args.notes), manifest_path, report)

    if args.as_json:
        print(json.dumps({
            "demoRoot": root,
            "notes": args.notes,
            "manifest": manifest_path,
            "passed": len(report.errors) == 0,
            "errorCount": len(report.errors),
            "warningCount": len(report.warnings),
            "issues": [i.as_dict() for i in report.issues],
        }, ensure_ascii=False, indent=2))
    else:
        print(render_text(report, root, args.notes, manifest_path))

    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
