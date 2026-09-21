#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_manifest.py — jf-* 最小渲染器（降级方案）

从 manifest.json 生成可跳转的多页 HTML 原型。不依赖任何外部 skill，
外部执行者（interaction-prd runtime / html-style-generator / cc-designer）接入后
可覆盖本渲染器；它们不存在时，链路靠本脚本跑通。

设计基线接入（Phase 2，读 manifest.design，外部基线优先）：
  - design.tokens 指向的文件存在 → 直接复用，不覆盖、不重新生成内置 tokens.css
  - design.components 同上（存在即复用，不覆盖产品自带交互脚本）
  - design.spec / design.states 文件存在 → 每页 meta 行标注「设计基线：DESIGN.md」
    并链接 components.html / states.html（均不带 data-nav，避免被当成页面跳转）
  - design 缺失或文件不存在 → 页面不挂设计基线徽标，改用内置简洁单色规范降级
  - 额外生成两个展示页：components.html（逐组件逐状态）/ states.html（跨模块五状态），
    数据源为 components-and-states.md；无该文件时按 manifest.components[] 骨架降级
    （这两页与 index.html 都是 PM chrome，**演示档不出**，见 --demo）

用法：
  python3 render_manifest.py <manifest.json> [--root DIR] [--out DIR] [--strict] [--demo]

  --strict  把降级情况作为 WARN 打到 stderr（声明的设计基线文件缺失、design 未声明、
            两个设计文档都不可用）。只提示不拦截：退出码仍为 0，渲染产物照常生成，
            「降级不阻塞」是刻意约定。
  --demo    客户演示档（第三产出档）：整棵树上不出现 PM chrome——每页摘掉标注徽标 /
            未落点区 / meta 行，**且不产出 index.html / components.html /
            states.html 三张 PM 展示页**；另出 console.html（场景控制台）顶替索引位。
            标注是设计评审的索引，不是给客户看的东西——两场会、两棵树，同一份
            manifest。摘 chrome 是**不产出**，不是 display:none：藏起来的东西客户
            按 Ctrl+U 照样看得见。正文里的进度口吻（「（错误文案待补）」「空态文案
            需与业务方确认」「列表页骨架」）同理不印——那是写给 PM 的「还没写完」，
            客户看到只会以为产品没做完；删尾注、**不另造文案**。

产物：
  <pages[].file>                     每页一个 HTML（按 manifest 声明的路径）
  prototypes/shared/tokens.css       token（外部存在则复用；否则内置简洁单色规范）
  prototypes/shared/components.js    共享交互脚本（状态切换 / modal 浮层 / 标注气泡）
  prototypes/index.html              入口索引（只列 standalone 页；**演示档不出**）
  prototypes/components.html         公共组件展示页（逐组件逐状态；**演示档不出**）
  prototypes/states.html             跨模块状态展示页（五状态；**演示档不出**）
  prototypes/console.html            演示控制台（仅 --demo；模块 → 场景 → 步骤）

渲染规则（对齐 jf-ia / jf-uxprompt 的 LF 约定）：
  - 侧边导航只列 standalone 页，按 module 分组
  - sub-flow 页不进导航树，只出现在宿主页的「从属与跳转」区
  - 每个跳转都是 <a href="./<id>.html" data-nav="<id>">，脱离工具也能点通
  - modal 关系在宿主页渲染为浮层按钮，JS 未加载时退化为整页跳转
  - 「从属与跳转」分四类：激活子流程 / 由谁激活 / 下钻·返回·相关 / 外部链接
  - annotations 渲染成**编号徽标 + 气泡浮层**（点徽标弹出标题/正文/状态）：
      1. target 已在页面 HTML 里（真实元素，或骨架元素）→ 徽标挂在那个元素上
      2. 注不进去 → 落到页面下部「评审标注 · 未落点」区并报 WARN，条目自己带锚点
    骨架元素的锚点用 data-annotation-anchor 标出（锚点表见 SKILL.md）：
    state-<状态> / rel-<from>-<to> / modal-<pageId>
    旧实现是「给自己造一个同名 id 混过 F4」——看着像落点了，实际把
    「这条标注没落到页面上」这件事藏了起来。
  - --demo 关掉每页的标注层、meta 行与状态正文的进度尾注，另出 console.html；
    控制台的场景步骤
    用 `<目标页>?state=<状态>` 传参，页内脚本加载后按它切状态，
    未加载则落 default（退化方向与 modal 一致）
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

TOKENS_CSS = """/* jf-* 内置简洁单色规范（降级方案）
   单一强调色 + 中性灰阶；外部 design-system 接入后由 DESIGN.md 覆盖
   规范：近白画布、近黑文字、发丝边框、小圆角、无渐变、轻阴影；
   强调色禁止使用 Tailwind 默认蓝紫（#3b82f6/#2563eb/#6366f1 等） */
:root {
  --jf-accent: #33557d;
  --jf-accent-weak: #edf2f6;
  --jf-accent-line: #c9d5e0;
  --jf-bg: #f7f8fa;
  --jf-surface: #ffffff;
  --jf-border: #e3e6ea;
  --jf-text: #1f2328;
  --jf-text-weak: #57606a;
  --jf-text-faint: #8b949e;
  --jf-danger: #c0392b;
  --jf-danger-weak: #fdf0ee;
  --jf-ok: #1a7f52;
  --jf-radius: 6px;
  --jf-space-1: 4px;
  --jf-space-2: 8px;
  --jf-space-3: 12px;
  --jf-space-4: 16px;
  --jf-space-5: 24px;
  --jf-space-6: 32px;
  --jf-font: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei",
             "Helvetica Neue", Arial, sans-serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--jf-bg);
  color: var(--jf-text);
  font-family: var(--jf-font);
  font-size: 14px;
  line-height: 1.6;
}

a { color: var(--jf-accent); text-decoration: none; }
a:hover { text-decoration: underline; }

.jf-shell { display: flex; min-height: 100vh; }

.jf-nav {
  width: 232px;
  flex: 0 0 232px;
  background: var(--jf-surface);
  border-right: 1px solid var(--jf-border);
  padding: var(--jf-space-4) 0;
}
.jf-nav-brand {
  padding: 0 var(--jf-space-4) var(--jf-space-4);
  font-weight: 600;
  border-bottom: 1px solid var(--jf-border);
  margin-bottom: var(--jf-space-3);
}
.jf-nav-group { padding: var(--jf-space-2) var(--jf-space-4) 0; }
.jf-nav-group-title {
  font-size: 12px;
  color: var(--jf-text-faint);
  letter-spacing: .04em;
}
.jf-nav-item {
  display: block;
  padding: 6px var(--jf-space-3);
  margin: 2px 0;
  border-radius: var(--jf-radius);
  color: var(--jf-text);
}
.jf-nav-item:hover { background: var(--jf-bg); text-decoration: none; }
.jf-nav-item.active {
  background: var(--jf-accent-weak);
  color: var(--jf-accent);
  font-weight: 600;
}
.jf-nav-num { color: var(--jf-text-faint); font-size: 12px; margin-right: 6px; }

.jf-main { flex: 1; min-width: 0; padding: var(--jf-space-5) var(--jf-space-6); }

.jf-header { margin-bottom: var(--jf-space-4); }
.jf-title { margin: 0; font-size: 22px; font-weight: 600; }
.jf-meta {
  margin-top: var(--jf-space-2);
  color: var(--jf-text-weak);
  font-size: 13px;
}
.jf-meta span { margin-right: var(--jf-space-4); white-space: nowrap; }
.jf-badge {
  display: inline-block;
  padding: 1px 8px;
  border: 1px solid var(--jf-accent-line);
  background: var(--jf-accent-weak);
  color: var(--jf-accent);
  border-radius: 999px;
  font-size: 12px;
  margin-right: var(--jf-space-2);
}
.jf-badge.weak { border-color: var(--jf-border); background: var(--jf-bg); color: var(--jf-text-weak); }

.jf-states { margin: var(--jf-space-3) 0 var(--jf-space-4); }
.jf-state-btn {
  display: inline-block;
  padding: 3px 10px;
  margin-right: var(--jf-space-2);
  border: 1px solid var(--jf-border);
  background: var(--jf-surface);
  border-radius: 999px;
  font-size: 12px;
  cursor: pointer;
  color: var(--jf-text-weak);
}
.jf-state-btn.active {
  border-color: var(--jf-accent);
  background: var(--jf-accent-weak);
  color: var(--jf-accent);
  font-weight: 600;
}

.jf-card {
  background: var(--jf-surface);
  border: 1px solid var(--jf-border);
  border-radius: var(--jf-radius);
  padding: var(--jf-space-4);
  margin-bottom: var(--jf-space-4);
}
.jf-card h3 { margin: 0 0 var(--jf-space-3); font-size: 15px; }

.jf-grid { display: grid; gap: var(--jf-space-3); }
.jf-grid.cols-3 { grid-template-columns: repeat(3, 1fr); }
.jf-grid.cols-2 { grid-template-columns: repeat(2, 1fr); }

.jf-kpi { border: 1px solid var(--jf-border); border-radius: var(--jf-radius); padding: var(--jf-space-3); }
.jf-kpi-label { color: var(--jf-text-weak); font-size: 12px; }
.jf-kpi-value { font-size: 24px; font-weight: 600; }
.jf-chart-placeholder {
  height: 160px;
  border: 1px dashed var(--jf-border);
  border-radius: var(--jf-radius);
  display: flex; align-items: center; justify-content: center;
  color: var(--jf-text-faint);
  background: var(--jf-bg);
}

table.jf-table { width: 100%; border-collapse: collapse; }
table.jf-table th, table.jf-table td {
  border-bottom: 1px solid var(--jf-border);
  padding: 8px var(--jf-space-2);
  text-align: left;
}
table.jf-table th { color: var(--jf-text-weak); font-weight: 600; font-size: 12px; }

.jf-field { margin-bottom: var(--jf-space-3); }
.jf-label { display: block; font-size: 12px; color: var(--jf-text-weak); margin-bottom: 4px; }
.jf-input {
  width: 100%;
  padding: 6px var(--jf-space-2);
  border: 1px solid var(--jf-border);
  border-radius: var(--jf-radius);
  background: var(--jf-surface);
  color: var(--jf-text-faint);
}
.jf-actions { margin-top: var(--jf-space-4); }
.jf-btn {
  display: inline-block;
  padding: 6px 14px;
  border-radius: var(--jf-radius);
  border: 1px solid var(--jf-accent);
  background: var(--jf-accent);
  color: #fff;
  cursor: pointer;
}
.jf-btn.ghost { background: var(--jf-surface); color: var(--jf-text); border-color: var(--jf-border); }

.jf-skeleton { height: 12px; border-radius: 4px; background: #eceff2; margin-bottom: var(--jf-space-2); }
.jf-empty { text-align: center; padding: var(--jf-space-6); color: var(--jf-text-faint); }
.jf-error {
  border: 1px solid #f0c9c2;
  background: var(--jf-danger-weak);
  color: var(--jf-danger);
  border-radius: var(--jf-radius);
  padding: var(--jf-space-3);
}

.jf-rel { margin-top: var(--jf-space-5); }
.jf-rel h3 { font-size: 14px; margin-bottom: var(--jf-space-2); }
.jf-rel ul { margin: 0 0 var(--jf-space-3); padding-left: 18px; }
.jf-rel li { margin-bottom: 4px; }
.jf-rel .kind { color: var(--jf-text-faint); font-size: 12px; margin-right: 6px; }

/* ---- 评审标注：编号徽标 + 气泡 ---- */
.jf-ann-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 18px; padding: 0 5px; margin-left: 6px;
  border: 1px solid var(--jf-accent); border-radius: 9px;
  background: var(--jf-surface); color: var(--jf-accent);
  font-size: 11px; line-height: 1; cursor: pointer; vertical-align: middle;
}
.jf-ann-badge:hover { background: var(--jf-accent); color: #fff; }
/* 修饰类既可以挂在徽标自己身上（正文内联落点），也可以挂在容器上（未落点条目） */
.jf-ann-badge.jf-ann--resolved, .jf-ann--resolved .jf-ann-badge {
  border-color: var(--jf-border); color: var(--jf-text-faint);
}
.jf-ann-badge.jf-ann--rejected, .jf-ann--rejected .jf-ann-badge {
  border-color: var(--jf-danger); color: var(--jf-danger);
}

.jf-ann-panel {
  margin-top: var(--jf-space-5); border: 1px dashed var(--jf-border);
  border-radius: var(--jf-radius); padding: var(--jf-space-3);
}
.jf-ann-panel h3 { font-size: 14px; margin: 0 0 var(--jf-space-1); color: var(--jf-danger); }
.jf-ann-panel .hint { font-size: 12px; color: var(--jf-text-faint); margin-bottom: var(--jf-space-3); }
.jf-ann-entry {
  display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap;
  border: 1px dashed var(--jf-border); border-radius: var(--jf-radius);
  padding: 6px 10px; margin-bottom: 6px; font-size: 12px; color: var(--jf-text-weak);
}
.jf-ann-entry .t { color: var(--jf-text); }

/* 全部标注的静态清单：<details> 原生折叠，关掉 JS 也能读到标注全文 */
.jf-ann-all { margin-top: var(--jf-space-5); font-size: 12px; }
.jf-ann-all summary { cursor: pointer; color: var(--jf-text-weak); }
.jf-ann-all .n { color: var(--jf-accent); }
.jf-ann-all .s { color: var(--jf-text-faint); }
.jf-ann-all .c { flex-basis: 100%; color: var(--jf-text-weak); }

.jf-bubble-backdrop {
  position: fixed; inset: 0; background: rgba(15, 23, 42, .28);
  display: flex; align-items: center; justify-content: center; z-index: 60;
}
.jf-bubble {
  background: var(--jf-surface); border-radius: var(--jf-radius);
  width: 380px; max-width: 90vw; padding: var(--jf-space-4);
  box-shadow: 0 8px 24px rgba(15, 23, 42, .18);
  border-left: 3px solid var(--jf-accent);
}
.jf-bubble h4 { margin: 0 0 var(--jf-space-2); }
.jf-bubble .meta { font-size: 12px; color: var(--jf-text-faint); margin-bottom: var(--jf-space-2); }
.jf-bubble-actions { margin-top: var(--jf-space-4); text-align: right; }
.jf-bubble--resolved { border-left-color: var(--jf-border); }
.jf-bubble--rejected { border-left-color: var(--jf-danger); }

.jf-modal-backdrop {
  position: fixed; inset: 0; background: rgba(15, 23, 42, .45);
  display: flex; align-items: center; justify-content: center; z-index: 50;
}
.jf-modal {
  background: var(--jf-surface); border-radius: var(--jf-radius);
  width: 420px; max-width: 90vw; padding: var(--jf-space-4);
  box-shadow: 0 8px 24px rgba(15, 23, 42, .14);
}
.jf-modal h4 { margin: 0 0 var(--jf-space-2); }
.jf-modal-actions { margin-top: var(--jf-space-4); text-align: right; }
.jf-modal-actions .jf-btn { margin-left: var(--jf-space-2); }

.jf-index { max-width: 720px; margin: 60px auto; }
.jf-index li { margin-bottom: 6px; }
"""

# 共享交互脚本：状态切换 + modal 浮层（每页通过 <script src> 引用，
# 与 tokens.css 一样是全站共享产物，避免逐页内联重复）
COMPONENTS_JS = """/* jf-* 共享交互脚本（降级方案）：状态切换 + modal 浮层 + 标注气泡 */
/* ?state=<状态> —— 客户演示档的控制台用 query 驱动目标页落态（见 console.html）。
   JS 未加载时这段不执行，页面停在 default：退化方向与「JS 未加载时 modal
   退化为整页跳转」一致，跳转协议的底线（原生相对 href 就能跳）不受影响。
   走 btn.click() 而不是手改 DOM：复用下面那条现成的切换路径，两边不会分叉。 */
(function () {
  var m = location.search.match(/[?&]state=([^&]*)/);
  if (!m) { return; }
  var s;
  try { s = decodeURIComponent(m[1]); } catch (err) { s = m[1]; }
  var btn = document.querySelector('.jf-state-btn[data-state="' + s + '"]');
  if (btn) { btn.click(); }
})();
document.addEventListener('click', function (e) {
  // 标注气泡要排在最前：徽标会插在链接/modal 触发器的**内部**，
  // 落在后面的分支上就会被当成外层元素，点徽标变成跳转或弹窗。
  var badge = e.target.closest && e.target.closest('.jf-ann-badge');
  if (badge) {
    var bub = document.getElementById(badge.getAttribute('data-bubble'));
    if (bub) { e.preventDefault(); bub.style.display = 'flex'; return; }
  }
  var bcloser = e.target.closest && e.target.closest('[data-bubble-close]');
  if (bcloser) {
    var b2 = document.getElementById(bcloser.getAttribute('data-bubble-close'));
    if (b2) { b2.style.display = 'none'; return; }
  }
  var btn = e.target.closest && e.target.closest('.jf-state-btn');
  if (btn) {
    var s = btn.getAttribute('data-state');
    document.querySelectorAll('.jf-state-btn').forEach(function (b) {
      b.classList.toggle('active', b === btn);
    });
    document.querySelectorAll('.jf-state-body').forEach(function (d) {
      d.style.display = (d.getAttribute('data-state-block') === s) ? '' : 'none';
    });
    return;
  }
  var link = e.target.closest && e.target.closest('a[data-modal]');
  if (link) {
    var id = 'modal-' + link.getAttribute('data-nav');
    var layer = document.getElementById(id);
    if (layer) { e.preventDefault(); layer.style.display = 'flex'; return; }
  }
  var closer = e.target.closest && e.target.closest('[data-modal-close]');
  if (closer) {
    var l2 = document.getElementById(closer.getAttribute('data-modal-close'));
    if (l2) { l2.style.display = 'none'; }
  }
});
document.addEventListener('keydown', function (e) {
  if (e.key !== 'Escape') { return; }
  document.querySelectorAll('.jf-bubble-backdrop, .jf-modal-backdrop').forEach(
    function (l) { l.style.display = 'none'; });
});
document.addEventListener('click', function (e) {
  if (e.target.classList &&
      (e.target.classList.contains('jf-modal-backdrop') ||
       e.target.classList.contains('jf-bubble-backdrop'))) {
    e.target.style.display = 'none';
  }
});
"""

STATE_LABELS = {
    "default": "默认",
    "hover": "悬停",
    "active": "按下",
    "empty": "空态",
    "loading": "加载中",
    "error": "错误态",
    "disabled": "禁用态",
    "permission-denied": "无权限",
    # 业务态（客户演示档的场景步骤用得上；见 manifest-schema.md 的 scenes[]）
    "editing": "编辑态",
    "warning": "警示态",
    "blocked": "拦截态",
    "success": "成功态",
}

# 组件四态 / 跨模块五状态（与 jf-design/references/design-contract.md 一致）
COMPONENT_STATES = ("default", "hover", "active", "disabled")
CROSS_STATES = ("empty", "loading", "error", "disabled", "permission-denied")

# manifest.design 的字段 → 降级提示用的默认语义
DESIGN_FIELDS = ("tokens", "components", "spec", "states")

FRAME_LABELS = {"route": "全幅 route 页", "modal": "弹窗 modal"}
KIND_LABELS = {
    "list": "列表页",
    "detail": "详情页",
    "form": "表单页",
    "dashboard": "看板页",
    "confirm": "确认弹窗",
    "external": "外部页",
}
SEMANTIC_LABELS = {
    "activate": "激活子流程",
    "drill": "下钻",
    "back": "返回",
    "rel": "相关",
}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


# 标注协议允许的两种稳定 selector 形式（与 validate_manifest.py 保持一致）
ANN_ID_RE = re.compile(r"^#([A-Za-z0-9_-]+)$")
ANN_ATTR_RE = re.compile(
    r"^\[\s*data-annotation-anchor\s*=\s*[\"']?([A-Za-z0-9_-]+)[\"']?\s*\]$")

# 标注气泡的三态。契约源：jf-contract/references/manifest-schema.md#annotations
# 与 jf-validate/scripts/validate_manifest.py 的 VALID_ANNOTATION_STATUS 人工对齐——
# 两个脚本分属不同 skill、各自以子进程运行，没法 import 共享；
# 一致性由 tests/unit/scripts/test_render_manifest.py 的用例盯着，不许漂。
ANNOTATION_STATUS = ("active", "resolved", "rejected")
ANNOTATION_STATUS_LABELS = {"active": "待确认", "resolved": "已答复", "rejected": "客户否决"}
DEFAULT_ANNOTATION_STATUS = "active"

# 标注区在页面模板里的占位：正文拼好之后才注入徽标，最后替换成未落点区 + 气泡浮层
ANN_SENTINEL = "<!--JF-ANNOTATION-SECTION-->"


def skeleton_anchor(value: str) -> str:
    """骨架元素的标注锚点属性。

    标注的 target 写 `[data-annotation-anchor=<value>]` 就能落到这个元素上。
    内置渲染器只给**它自己生成的**元素种锚点（锚点表见 SKILL.md）；
    真实业务元素（「批量审批」按钮之类）不归它管——骨架里本来就没有那个元素，
    编一个假的当落点等于骗评审，所以那种标注一律进「未落点」区报出来。
    """
    return ' data-annotation-anchor="%s"' % esc(value)


def inject_badge(html_text: str, target: str, badge: str) -> str | None:
    """把徽标插到 target 命中的元素**开标签之后**。

    只做一次、只做第一个命中——注入的是渲染器自己生成的 HTML，元素形态已知，
    不做 DOM 解析。返回 None 表示没命中（调用方据此走「未落点」）。

    前提：正文里没有 HTML 注释包着的元素。模板目前除标注占位外不含任何注释；
    模板里一旦出现注释，注释里的标签会成为新的假落点。
    """
    m = ANN_ID_RE.match(target)
    attr = "id" if m else "data-annotation-anchor"
    if not m:
        m = ANN_ATTR_RE.match(target)
    if not m:
        return None
    # 两种引号都认（注入不该比「能不能定位」更严）；`(?<![-\w])` 挡住
    # data-id="x" / dataid="x" 这类靠词边界混进来的同名属性。
    pat = r'(<[a-zA-Z][^>]*?(?<![-\w])%s=["\']%s["\'][^>]*>)' \
        % (attr, re.escape(m.group(1)))
    new, n = re.subn(pat, lambda mo: mo.group(1) + badge, html_text, count=1)
    return new if n else None


def rel_href(page_file: str, target_file: str) -> str:
    """target 相对 page 的链接（同目录时退化为 ./x.html）"""
    page_dir = os.path.dirname(page_file) or "."
    rel = os.path.relpath(target_file, page_dir)
    return rel.replace(os.sep, "/")


def href_between(root: str, src_rel: str, dst_rel: str) -> str:
    """src_rel → dst_rel 的相对链接，两边都是相对 root 的路径。

    ⚠️ 必须先 join(root) 再 relpath：直接用声明值算相对路径，在
    「manifest 在 A 仓、产物落在 B 卷」时会把路径算到仓外去
    （本项目出过一次跨仓相对路径的线上事故，别再犯）。
    """
    src_abs = os.path.join(root, src_rel)
    dst_abs = os.path.join(root, dst_rel)
    rel = os.path.relpath(dst_abs, os.path.dirname(src_abs))
    return rel.replace(os.sep, "/")


def prototypes_root(first_page_file: str) -> str:
    """原型根目录：页面目录的上一级（index.html 所在处）。

    页面已经在根目录时（没有上一级）不再往外走，免得产物写到 root 之外。
    """
    first_dir = os.path.dirname(first_page_file) or "."
    up = os.path.normpath(os.path.join(first_dir, ".."))
    return first_dir if up.startswith("..") else up


# --------------------------------------------------------------------------- #
# 设计基线（manifest.design）
# --------------------------------------------------------------------------- #

MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$")
MD_TABLE_SEP_RE = re.compile(r":?-{2,}:?")
CODE_SPAN_RE = re.compile(r"`([^`]*)`")
# 组件类型：交互组件四态必须全 ✓；容器组件四态可标 —，但要在表下写落点说明。
# 与 check_design.py 的 COMPONENT_KINDS / CONTAINER_NOTE_RE 必须一致——
# 契约、门禁、渲染器三边对同一份 Markdown 的读法不能有分歧。
COMPONENT_KINDS = ("交互", "容器")
CONTAINER_NOTE_RE = re.compile(r"^\s*[-*]\s*`?([A-Za-z0-9_-]+)`?\s*[:：]\s*(.*)$")


def strip_ticks(s) -> str:
    """去掉 Markdown 行内代码标记：`a` → a。

    一格可能有多个 code span（如「引用 token」列 `--jf-a`、`--jf-b`），
    整串 strip("`") 只吃最外两个反引号、会把中间的留在文本里，
    所以按 span 配对去标记，落单的反引号再兜底去掉。
    """
    text = str(s if s is not None else "").strip()
    return CODE_SPAN_RE.sub(r"\1", text).replace("`", "").strip()


def container_note_map(sections: dict) -> dict:
    """「组件×状态」表下以 `- \\`<id>\\`：` 开头的落点说明 → {id: 说明}。

    容器类组件（页面外壳、表格）自己没有交互，四态的落点在其子部件上。
    这段散文此前只活在 Markdown 里，渲染出的组件页看不到它，
    于是页面给页面外壳画了一颗并不存在的「主操作」按钮。
    """
    _title, _rows, body = find_state_table(sections, ("组件",), "id")
    notes = {}
    for line in body:
        m = CONTAINER_NOTE_RE.match(line)
        if m:
            notes[m.group(1)] = m.group(2).strip()
    return notes


def split_md_sections(text: str) -> dict:
    """按标题切段：{标题: 正文行列表}（任意级别标题都切）。"""
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = MD_HEADING_RE.match(line)
        if m:
            current = m.group(1)
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def parse_md_table(body_lines) -> list:
    """把段落里的第一条 markdown 表解析成 [{列名: 单元格}]；无表返回 []。"""
    header = None
    out = []
    for line in body_lines:
        s = line.strip()
        if not s.startswith("|"):
            if header is not None:
                break  # 表到此为止
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(MD_TABLE_SEP_RE.fullmatch(c) for c in cells if c):
            continue  # 分隔行 |---|---|
        if header is None:
            header = [strip_ticks(c) for c in cells]
            continue
        out.append({header[i]: c for i, c in enumerate(cells) if i < len(header)})
    return out


def find_state_table(sections: dict, keywords, header_key: str, exclude=()) -> tuple:
    """按标题关键词找段落，返回其中表头含 header_key 的第一张表。

    只认「表头含 header_key」的表，不认光有标题的段落：契约模板的 H1
    （`# components-and-states.md — <产品名> 组件×状态契约`）也含「组件」二字，
    但正文无表——只看标题会挑错段落。
    """
    for title, body in sections.items():
        if not any(k in title for k in keywords) or any(e in title for e in exclude):
            continue
        rows = parse_md_table(body)
        if rows and header_key in rows[0]:
            # 连正文行一起回：表下的落点说明（`- \`<id>\`：`）不在表里，
            # 只有拿到原始行才能读出来
            return title, rows, body
    return None, [], []


def resolve_design(manifest: dict, root: str) -> dict:
    """解析 manifest.design，把「声明了」和「文件真的在」分成两件事。

    只声明不落盘是常态（先定契约后补图），所以这里不报错只记录，
    由调用方决定是降级渲染还是 --strict 提示。
    """
    declared = manifest.get("design")
    declared = declared if isinstance(declared, dict) else {}
    ctx = {"declared": bool(declared), "wired": False, "missing": []}
    for field in DESIGN_FIELDS:
        ctx["%s_rel" % field] = None
        ctx["%s_path" % field] = None
        rel = declared.get(field)
        if not rel:
            continue
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            ctx["%s_rel" % field] = rel
            ctx["%s_path" % field] = path
        else:
            ctx["missing"].append((field, rel))
    # 「接上了」= 至少有一份设计文档可供挂徽标；只有 tokens 不算
    ctx["wired"] = bool(ctx["spec_path"] or ctx["states_path"])
    return ctx


def design_badge(page_file: str, design: dict) -> str:
    """页面 meta 行的设计基线徽标。

    降级时返回空串（宁可不标，也不给「已有设计基线」的假信号）。
    """
    if not design.get("wired"):
        return ""
    bits = []
    spec_rel = design.get("spec_rel")
    if spec_rel:
        bits.append('设计基线：<a href="%s">DESIGN.md</a>'
                    % esc(href_between(design["root"], page_file, spec_rel)))
    else:
        bits.append("设计基线：DESIGN.md（缺）")
    for key, label in (("components_page", "组件×状态"), ("states_page", "跨模块状态")):
        rel = design.get(key)
        if rel:
            bits.append('<a href="%s">%s</a>'
                        % (esc(href_between(design["root"], page_file, rel)), esc(label)))
    return '<span class="jf-badge">%s</span>' % " ｜ ".join(bits)


def component_entries(manifest: dict, design: dict) -> list:
    """组件×状态展示数据。

    优先读 design.states 的「组件×状态」表；文件缺失/无表时降级为
    manifest.components[] 骨架（四态占位并标注待补）。
    """
    if design.get("states_rel"):
        try:
            with open(design["states_path"], encoding="utf-8") as f:
                sections = split_md_sections(f.read())
        except OSError:
            sections = {}
        _title, rows, _body = find_state_table(sections, ("组件",), "id")
        notes = container_note_map(sections)
        entries = []
        for row in rows:
            cid = strip_ticks(row.get("id"))
            if not cid:
                continue
            extra = [strip_ticks(t) for t in
                     re.split(r"[、,/\s]+", strip_ticks(row.get("其他状态")))]
            kind = strip_ticks(row.get("类型"))
            entries.append({
                "id": cid,
                "title": strip_ticks(row.get("组件")) or cid,
                "kind": kind if kind in COMPONENT_KINDS else "交互",
                "note": notes.get(cid, ""),
                "extra": [t for t in extra if t and t != "—"],
                "tokens": strip_ticks(row.get("引用 token")),
                "usedBy": strip_ticks(row.get("usedBy")),
                "from_doc": True,
            })
        if entries:
            return entries

    return [{"id": c["id"], "title": c.get("title") or c["id"], "kind": "交互",
             "note": "", "extra": [],
             "tokens": "", "usedBy": "、".join(c.get("usedBy") or []),
             "from_doc": False}
            for c in (manifest.get("components") or [])
            if isinstance(c, dict) and c.get("id")]


def cross_state_entries(design: dict) -> list:
    """跨模块五状态展示数据；文档缺失时给骨架并标注待补。"""
    rows = []
    if design.get("states_rel"):
        try:
            with open(design["states_path"], encoding="utf-8") as f:
                sections = split_md_sections(f.read())
        except OSError:
            sections = {}
        _title, rows, _body = find_state_table(sections, ("跨模块", "状态"), "状态",
                                        exclude=("组件",))
    by_id = {}
    for row in rows:
        sid = strip_ticks(row.get("状态"))
        if sid:
            by_id[sid] = row
    return [{"id": sid,
             "scene": (by_id.get(sid) or {}).get("触发场景", ""),
             "visual": (by_id.get(sid) or {}).get("视觉表现", ""),
             "copy": (by_id.get(sid) or {}).get("文案口径", ""),
             "owner": strip_ticks((by_id.get(sid) or {}).get("落点组件")),
             "defined": sid in by_id}
            for sid in CROSS_STATES]


# --------------------------------------------------------------------------- #
# 内容骨架
# --------------------------------------------------------------------------- #

def render_state_body(page: dict, state: str, relations_out,
                      demo: bool = False) -> str:
    """状态正文。`demo`（客户演示档）只改一件事：不印内部口吻的进度尾注。

    「（错误文案待补）」「空态文案需与业务方确认」这类字是写给 PM 的进度提示
    （文案还没写），客户看到只会以为产品没做完。演示档**删尾注、不另造文案**
    —— 编一句像真的业务话术比留白更假，「说人话 / 可执行 / 一致」是人工过的事
    （jf-uxprompt 演示档纪律第 4 条），不是渲染器该猜的。评审树照旧全留。
    """
    kind = page.get("kind", "list")
    title = page.get("title", "")
    obj = page.get("obj") or "数据"
    rows = 4 if state == "loading" else 3

    if state == "loading":
        return "".join('<div class="jf-skeleton" style="width:%d%%"></div>' % w
                       for w in (92, 78, 86, 64)[:rows])
    if state == "empty":
        note = "" if demo else ('<br><span style="font-size:12px">'
                                '空态文案需与业务方确认</span>')
        return '<div class="jf-empty">暂无%s%s</div>' % (esc(obj), note)
    if state == "error":
        note = "" if demo else "（错误文案待补）"
        return ('<div class="jf-error"><strong>加载失败</strong><br>'
                '%s数据获取异常，请重试或联系管理员%s</div>' % (esc(title), note))
    if state == "disabled":
        note = "" if demo else "（禁用态，触发条件待补）"
        return ('<div class="jf-error" style="border-color:var(--jf-border);'
                'background:var(--jf-bg);color:var(--jf-text-weak)">'
                '当前状态不可用%s</div>' % note)
    if state == "permission-denied":
        return ('<div class="jf-error" style="border-color:var(--jf-border);'
                'background:var(--jf-bg);color:var(--jf-text-weak)">'
                '无访问权限（请联系管理员开通）</div>')
    # 业务态：只在页面 states 里声明过才走得到这里（I12 管场景步骤的取值）。
    # 不写这四支的话，未识别的状态会一路落到下面的 kind 分支——
    # 也就是「按 default 渲染」：?state=warning 出来一个和 default 一模一样的
    # 页面，演示时是静默的谎，比报错难查得多。
    if state == "editing":
        note = "" if demo else ('<br><span style="font-size:12px">'
                                '可编辑项与校验规则待补</span>')
        return '<div class="jf-empty">编辑态：字段进入可编辑状态%s</div>' % note
    if state == "warning":
        note = "" if demo else "（预警规则待补）"
        return ('<div class="jf-error" style="border-color:var(--jf-danger);'
                'background:var(--jf-danger-weak)">'
                '警示态：触发业务预警，需确认后继续%s</div>' % note)
    if state == "blocked":
        note = "" if demo else "<br>触发拦截的业务规则待补"
        return '<div class="jf-error"><strong>操作被拦截</strong>%s</div>' % note
    if state == "success":
        return ('<div class="jf-empty" style="border-color:var(--jf-ok);'
                'color:var(--jf-ok)">成功态：操作已完成</div>')

    # default
    if kind == "list":
        return (
            '<table class="jf-table"><thead><tr>'
            '<th style="width:32%">名称</th><th>状态</th><th>负责人</th><th>更新时间</th>'
            '</tr></thead><tbody>'
            + "".join(
                '<tr><td><a href="%s">示例%s %d</a></td><td>进行中</td>'
                '<td>—</td><td>2026-09-01</td></tr>' % (first_detail_href(relations_out), esc(obj), i + 1)
                for i in range(3))
            + "</tbody></table>"
        )
    if kind == "detail":
        items = [("编号", "DEMO-001"), ("名称", "示例%s" % esc(obj)),
                 ("状态", "进行中"), ("负责人", "—"), ("创建时间", "2026-09-01"),
                 ("备注", "示例数据" if demo else "示例数据仅占位")]
        return ('<div class="jf-grid cols-2">'
                + "".join('<div><div class="jf-kpi-label">%s</div><div>%s</div></div>'
                          % (esc(k), v) for k, v in items)
                + "</div>")
    if kind == "form":
        fields = [("名称", "请输入%s名称" % esc(obj)),
                  ("类型", "下拉选择"),
                  ("说明", "多行文本"),
                  ("附件", "上传文件")]
        return ("".join('<div class="jf-field"><label class="jf-label">%s</label>'
                        '<div class="jf-input">%s</div></div>' % (esc(k), esc(v))
                        for k, v in fields)
                + '<div class="jf-actions"><span class="jf-btn">提交</span>'
                  '<span class="jf-btn ghost" style="margin-left:8px">取消</span></div>')
    if kind == "dashboard":
        chart = "图表（示例）" if demo else "图表占位（图表类型与指标待确认）"
        return ('<div class="jf-grid cols-3">'
                + "".join('<div class="jf-kpi"><div class="jf-kpi-label">%s</div>'
                          '<div class="jf-kpi-value">—</div></div>' % esc(t)
                          for t in ("总数", "进行中", "已完成"))
                + '</div><div class="jf-chart-placeholder" style="margin-top:16px">'
                + chart + '</div>')
    if kind == "confirm":
        return ('<div>确认执行该操作？此动作不可撤销。</div>'
                '<div class="jf-actions"><span class="jf-btn">确认</span>'
                '<span class="jf-btn ghost" style="margin-left:8px">取消</span></div>')
    if kind == "external":
        url = page.get("externalUrl") or "#"
        return ('<div class="jf-card">该页面指向外部系统：'
                '<a href="%s" target="_blank" rel="noopener">%s</a></div>'
                % (esc(url), esc(url)))
    return '<div class="jf-empty">未识别的页面类型：%s</div>' % esc(kind)


def first_detail_href(relations_out):
    """列表行链接到第一条 drill 关系目标；没有时用 #"""
    for href, label in relations_out:
        if href:
            return href
    return "#"


# --------------------------------------------------------------------------- #
# 评审标注：编号徽标 + 气泡
# --------------------------------------------------------------------------- #

def ann_slug(value) -> str:
    """把标注 id / 页面 id 收敛成可安全放进 HTML id 的片段。"""
    return re.sub(r"[^A-Za-z0-9_-]", "-", str(value or ""))


def annotation_records(manifest: dict, pid: str) -> list:
    """归一化本页的标注：徽标 HTML + 气泡 HTML + 三态。

    状态缺省视作 active；非法值在这里退回 active（门禁 S0 会单独报错，
    渲染器不重复拦截——但也绝不把非法值原样写进 class）。

    气泡 id 由渲染器按页内序号编排并**保证唯一**，不直接信任 manifest 里的
    标注 id：作者写的 id 可能重复，或与按序号兜底的那条撞形（`a.1` 与 `a-1`
    经 ann_slug 同形）。撞了就是两个同 id 元素 + 两个同 data-bubble 的徽标，
    `getElementById` 只返回第一个——**点第二条徽标弹出的是第一条的正文**。
    """
    anns = manifest.get("annotations")
    if not isinstance(anns, dict):
        # annotations 写成数组之类：S0 会报错，渲染器不裸抛栈
        # （其余字段写错时都是降级 + 门禁报错，这里保持一致）
        return []
    records = []
    used = set()
    for i, a in enumerate(anns.get(pid) or []):
        if not isinstance(a, dict):
            continue
        status = a.get("status")
        if status not in ANNOTATION_STATUS:
            status = DEFAULT_ANNOTATION_STATUS
        number = a.get("number", i + 1)
        bubble_id = "ann-%s-%s" % (ann_slug(pid), ann_slug(a.get("id") or (i + 1)))
        base, k = bubble_id, 1
        while bubble_id in used:
            k += 1
            bubble_id = "%s-%d" % (base, k)
        used.add(bubble_id)
        rec = {
            "id": a.get("id") or "",
            "number": number,
            "title": a.get("title") or "",
            "content": a.get("content") or "",
            "target": a.get("target") or "",
            "status": status,
            "bubble_id": bubble_id,
        }
        rec["badge"] = ('<span class="jf-ann-badge jf-ann--%s" data-bubble="%s"'
                        ' title="%s">%s</span>'
                        % (esc(status), esc(rec["bubble_id"]),
                           esc(rec["title"] or "评审标注"), esc(number)))
        rec["bubble"] = _bubble_html(rec)
        records.append(rec)
    return records


def _bubble_html(rec: dict) -> str:
    meta = "｜".join(x for x in (
        ("标注 %s" % esc(rec["id"])) if rec["id"] else "",
        "状态：%s" % esc(ANNOTATION_STATUS_LABELS.get(rec["status"], rec["status"])),
        ("目标：%s" % esc(rec["target"])) if rec["target"] else "",
    ) if x)
    body = ("<div>%s</div>" % esc(rec["content"])) if rec["content"] else ""
    return ('<div class="jf-bubble-backdrop" id="%s" style="display:none">'
            '<div class="jf-bubble jf-bubble--%s">'
            '<h4>%s %s</h4><div class="meta">%s</div>%s'
            '<div class="jf-bubble-actions">'
            '<span class="jf-btn ghost" data-bubble-close="%s">关闭</span>'
            '</div></div></div>'
            % (esc(rec["bubble_id"]), esc(rec["status"]), esc(rec["number"]),
               esc(rec["title"]), meta, body, esc(rec["bubble_id"])))


def _ann_panel_html(entries: list) -> str:
    """未落点区：target 在页面上找不到元素时，标注退到这里。

    区标题明写「页面上还没有对应元素」—— 旧实现给自己造一个同名 id 混过 F4，
    看着像落点了，实际把「这条没落到页面上」这件事藏了起来。
    """
    if not entries:
        return ""
    rows = ""
    for rec, anchor_attr in entries:
        content = ("<span>%s</span>" % esc(rec["content"])) if rec["content"] else ""
        rows += ('<div class="jf-ann-entry jf-ann--%s"%s>%s<span class="t">%s</span>%s</div>'
                 % (esc(rec["status"]), anchor_attr, rec["badge"],
                    esc(rec["title"]), content))
    return ('<div class="jf-ann-panel"><h3>评审标注 · 未落点（%d 条）</h3>'
            '<div class="hint">这些标注的 target 在页面上还没有对应元素。'
            '骨架里的元素用 <code>[data-annotation-anchor=…]</code> 定位（锚点表见 SKILL.md）；'
            '真实业务元素由外部执行者或真实页面内容提供。'
            '气泡照样点得开，评审时按编号逐条过。</div>%s</div>'
            % (len(entries), rows))


def _ann_all_html(records: list) -> str:
    """全部标注的静态清单——落实「关掉 JS 也要能读到标注全文」。

    气泡是浮层：`display:none` + JS 打开，脚本被禁 / 报错时正文就够不着了。
    `<details>` 是原生元素，折叠展开不依赖 JS，所以这份清单在无脚本时照样可读。
    内容不重复丢失：落点标注的正文只活在气泡里，这份清单是它唯一的静态副本。
    """
    if not records:
        return ""
    rows = ""
    for rec in records:
        rows += ('<div class="jf-ann-entry jf-ann--%s">'
                 '<span class="n">%s</span><span class="t">%s</span>'
                 '<span class="s">%s</span>'
                 '<div class="c">%s</div></div>'
                 % (esc(rec["status"]), esc(rec["number"]), esc(rec["title"]),
                    esc(ANNOTATION_STATUS_LABELS.get(rec["status"], rec["status"])),
                    esc(rec["content"])))
    return ('<details class="jf-ann-all"><summary>评审标注全览（%d 条）</summary>%s'
            '</details>' % (len(records), rows))


def _ann_anchor_attr(target: str) -> str:
    """未落点条目自己带上的锚点——保证 F4 仍有落点可查。"""
    m = ANN_ID_RE.match(target)
    if m:
        return ' id="%s"' % esc(m.group(1))
    m = ANN_ATTR_RE.match(target)
    if m:
        return ' data-annotation-anchor="%s"' % esc(m.group(1))
    return ""


# --------------------------------------------------------------------------- #
# 页面渲染
# --------------------------------------------------------------------------- #

def render_page(manifest: dict, page: dict, by_id: dict, css_rel: str, js_rel: str,
                design: dict | None = None, demo: bool = False) -> str:
    pid = page["id"]
    product = manifest.get("product", {})
    modules = {m.get("id"): m for m in manifest.get("modules", []) if isinstance(m, dict)}
    pages = [p for p in manifest.get("pages", []) if isinstance(p, dict)]
    relations = [r for r in manifest.get("relations", []) if isinstance(r, dict)]

    page_file = page["file"]
    target_of = {}

    def link_to(target_id: str, label: str, modal: bool = False) -> str:
        t = by_id.get(target_id)
        if not t or not t.get("file"):
            return esc(label)
        href = rel_href(page_file, t["file"])
        target_of[target_id] = True
        modal_attr = ' data-modal="1"' if modal else ""
        return '<a href="%s" data-nav="%s"%s%s>%s</a>' % (
            esc(href), esc(target_id), modal_attr,
            skeleton_anchor("rel-%s-%s" % (pid, target_id)), esc(label))

    # ---- 侧边导航（只列 standalone） ----
    nav_html = ['<div class="jf-nav-brand">%s</div>' % esc(product.get("name", "原型"))]
    grouped = {}
    for p in pages:
        if p.get("nav") != "standalone":
            continue
        grouped.setdefault(p.get("moduleId"), []).append(p)
    for mid, group in grouped.items():
        m = modules.get(mid, {})
        num = m.get("navNumber")
        nav_html.append('<div class="jf-nav-group"><div class="jf-nav-group-title">'
                        '%s%s</div>' % (("%s " % esc(num)) if num else "", esc(m.get("title", mid))))
        for p in group:
            href = rel_href(page_file, p["file"])
            active = " active" if p["id"] == pid else ""
            nav_html.append('<a class="jf-nav-item%s" href="%s" data-nav="%s">%s</a>'
                            % (active, esc(href), esc(p["id"]), esc(p.get("title", p["id"]))))
        nav_html.append("</div>")

    # ---- meta 行 ----
    crud = page.get("crud") or ""
    crud_txt = crud + ("（%s）" % page["crudNote"] if page.get("crudNote") else "")
    meta = [
        '<span>模块：%s</span>' % esc(modules.get(page.get("moduleId"), {}).get("title", page.get("moduleId"))),
        '<span>框架：%s</span>' % esc(FRAME_LABELS.get(page.get("frame"), page.get("frame"))),
        '<span>对象：%s｜%s</span>' % (esc(page.get("obj")), esc(crud_txt)),
        '<span>视口：%s×%s</span>' % (esc(page.get("viewport", {}).get("width")),
                                      esc(page.get("viewport", {}).get("height"))),
    ]
    if page.get("fr"):
        meta.append('<span>FR：%s</span>' % esc(", ".join(page["fr"])))
    badges = design_badge(page_file, design or {})
    if page.get("nav") == "sub-flow":
        badges += '<span class="jf-badge weak">子流程页</span>'
        if page.get("hostPageId"):
            badges += '<span class="jf-badge weak">宿主：%s</span>' % esc(
                by_id.get(page["hostPageId"], {}).get("title", page["hostPageId"]))
    if page.get("frame") == "modal":
        badges += '<span class="jf-badge weak">弹窗</span>'
    # 演示档整条 meta 行都不出：meta spans（pageId/moduleId/crud/fr）与 badges
    # （设计基线 / 子流程页 / 宿主 / 弹窗）都是渲染器自曝的内部元信息，
    # 客户看的应该是「一款正常产品」，不是带着归属标签的评审稿。
    meta_row = "" if demo else ('<div class="jf-meta">%s%s</div>'
                                % (badges, "".join(meta)))

    # ---- 状态切换 + 各状态内容 ----
    states = page.get("states") or ["default"]
    state_btns = "".join(
        '<span class="jf-state-btn%s" data-state="%s"%s>%s</span>'
        % (" active" if s == "default" else "", esc(s), skeleton_anchor("state-%s" % s),
           esc(STATE_LABELS.get(s, s))) for s in states)
    rel_links = [(rel_href(page_file, by_id[r["to"]]["file"]), r.get("label"))
                 for r in relations
                 if r.get("from") == pid and r.get("to") in by_id
                 and by_id[r["to"]].get("file")]
    state_blocks = "".join(
        '<div class="jf-state-body" data-state-block="%s"%s>%s</div>'
        % (esc(s), "" if s == "default" else ' style="display:none"',
           render_state_body(page, s, rel_links, demo))
        for s in states)

    # ---- 从属与跳转区 ----
    def rel_list(items):
        if not items:
            return ""
        return "<ul>" + "".join("<li>%s</li>" % i for i in items) + "</ul>"

    activate = [link_to(p["id"], "%s（激活子流程）" % p.get("title", p["id"]))
                for p in pages
                if p.get("hostPageId") == pid and p.get("nav") == "sub-flow"]
    activated_by = []
    if page.get("nav") == "sub-flow" and page.get("hostPageId"):
        activated_by.append(link_to(page["hostPageId"],
                                    "%s（由谁激活）" % by_id.get(page["hostPageId"], {})
                                    .get("title", page["hostPageId"])))
    drill, back, other, external_links = [], [], [], []
    for r in relations:
        if r.get("from") != pid:
            continue
        tid = r.get("to")
        if tid not in by_id:
            continue
        label = "%s → %s" % (esc(r.get("label") or "跳转"),
                             esc(by_id[tid].get("title", tid)))
        semantic = r.get("semantic") or "rel"
        cond = "（%s）" % esc(r["condition"]) if r.get("condition") else ""
        item = link_to(tid, label, modal=(r.get("type") == "modal")) + cond
        if r.get("type") == "external" or by_id[tid].get("kind") == "external":
            external_links.append(item)
        elif semantic == "drill":
            drill.append(item)
        elif semantic == "back":
            back.append(item)
        else:
            # activate 且目标已是本页子流程页时，链接已在「激活子流程」区出现，
            # 此处不重复；其余（含 activate 到非子流程目标）归入「相关」
            if not (semantic == "activate" and tid in {p["id"] for p in pages
                                                       if p.get("hostPageId") == pid}):
                other.append(item)

    rel_sections = ""
    for title, items in (("激活子流程", activate), ("由谁激活", activated_by),
                         ("下钻 · 返回 · 相关", drill + back + other),
                         ("外部链接", external_links)):
        if items:
            rel_sections += ('<div class="jf-rel"><h3>%s</h3>%s</div>'
                             % (title, rel_list(items)))

    # ---- 评审标注：徽标落点与气泡 ----
    # 徽标要插进正文元素内部，所以这里只备好记录，等页面拼装完再注入（见函数尾）。
    # 演示档不出标注层：传空列表而不是跳过 finish_annotations——后者会把
    # 字面量占位符留在页面里；空列表这条路经 place_annotations 得空 entries，
    # panel / 全览 / 气泡三者都返回 ""，最终 replace(SENTINEL, "") 干净摘掉。
    ann_records = [] if demo else annotation_records(manifest, pid)

    # ---- modal 浮层（本页可打开的弹窗） ----
    modal_layers = ""
    for p in pages:
        if p.get("frame") == "modal" and p.get("hostPageId") == pid:
            mid = "modal-%s" % p["id"]
            modal_layers += (
                '<div class="jf-modal-backdrop" id="%s"%s style="display:none">'
                '<div class="jf-modal"><h4>%s</h4>'
                '<div>%s</div>'
                '<div class="jf-modal-actions">'
                '<a class="jf-btn ghost" href="%s" data-nav="%s">在独立页打开</a>'
                '<span class="jf-btn" data-modal-close="%s">关闭</span>'
                '</div></div></div>'
                % (esc(mid), skeleton_anchor("modal-%s" % p["id"]),
                   esc(p.get("title", p["id"])),
                   # 演示档不出 note：schema 把 pages[].note 定义为「评审要点、待确认」
                   # （jf-interview 的待确认沿它追溯），是内部内容、不是客户文案。
                   esc("" if demo else (p.get("note") or "弹窗内容为占位")),
                   esc(rel_href(page_file, p["file"])), esc(p["id"]), esc(mid)))

    html_out = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s · %(product)s</title>
<link rel="stylesheet" href="%(css)s">
</head>
<body>
<div class="jf-shell">
  <nav class="jf-nav">%(nav)s</nav>
  <main class="jf-main">
    <div class="jf-header">
      <h1 class="jf-title">%(title)s</h1>
      %(meta_row)s
    </div>
    <div class="jf-states">%(state_btns)s</div>
    <div class="jf-card">
      %(kind_row)s
      %(state_blocks)s
    </div>
    %(rel_sections)s
    %(ann_section)s
  </main>
</div>
%(modal_layers)s
<script src="%(js)s"></script>
</body>
</html>
""" % {
        "title": esc(page.get("title", pid)),
        "product": esc(product.get("name", "原型")),
        "css": esc(css_rel),
        "js": esc(js_rel),
        "nav": "\n    ".join(nav_html),
        "meta_row": meta_row,
        "state_btns": state_btns,
        # 「XX页骨架」是渲染器自曝的实现口吻（客户看到的是骨架不是产品），演示档不出
        "kind_row": "" if demo else ("<h3>%s骨架</h3>"
                                     % esc(KIND_LABELS.get(page.get("kind"),
                                                           page.get("kind")))),
        "state_blocks": state_blocks,
        "rel_sections": rel_sections,
        "ann_section": "" if demo else ANN_SENTINEL,
        "modal_layers": modal_layers,
    }
    return finish_annotations(html_out, pid, ann_records)


def place_annotations(html_text: str, records: list) -> tuple[str, list]:
    """把徽标注入正文；注不进去的进「未落点」区。

    三支判定：
      1. target 命中页面正文里的真实元素 → 徽标挂到该元素上，真气泡
      2. target 命中渲染器给自己种的骨架锚点 → 同上（同样走第 1 支的注入路径）
      3. 都注不进去 → 退到「未落点」区，条目自己带锚点保 F4 可过，并报 WARN
    返回 (最终 HTML, 未落点记录列表)。
    """
    unlanded = []
    # 倒序注入：徽标一律紧贴开标签插入，正序注入会让同一锚点上的多条标注
    # 在页面上按编号倒着排（后注的离标签更近），评审顺着编号点会和视觉顺序打架。
    for rec in reversed(records):
        new_html = inject_badge(html_text, rec["target"], rec["badge"]) \
            if rec["target"] else None
        if new_html is None:
            unlanded.append(rec)
        else:
            html_text = new_html
    unlanded.reverse()  # 未落点区仍按 manifest 顺序列

    # 未落点条目自己带锚点（F4 仍要有落点可查）；
    # 同一个 target 只挂一次，否则会在同一页里冒出重复 id。
    used = set()
    entries = []
    for rec in unlanded:
        attr = ""
        if rec["target"] and rec["target"] not in used:
            attr = _ann_anchor_attr(rec["target"])
            if attr:
                used.add(rec["target"])
        entries.append((rec, attr))
    return html_text, entries


def finish_annotations(html_text: str, pid: str, records: list) -> str:
    """注入徽标 + 拼装未落点区、静态全览与气泡浮层，替换模板占位。"""
    if records and ANN_SENTINEL not in html_text:
        # 占位丢了就整段标注凭空消失——静默丢内容比报错难查得多（改模板时踩过）。
        # 检查放在注入**之前**：徽标注了却没有气泡可开，页面会挂着一个个点不动、
        # 点了还会顺着外层 <a> 跳走的死徽标，比什么都没有更难查。
        print("WARN 评审标注：页面 %s 的模板里没有标注区占位 %s，"
              "%d 条标注既不挂徽标、也无处可读" % (pid, ANN_SENTINEL, len(records)),
              file=sys.stderr)
        return html_text
    html_text, entries = place_annotations(html_text, records)
    bubbles = "".join(rec["bubble"] for rec in records)
    panel = _ann_panel_html(entries)
    if entries:
        print("WARN 评审标注：页面 %s 有 %d 条标注的 target 在页面上找不到元素，"
              "已放入「未落点」区：%s"
              % (pid, len(entries),
                 "、".join(rec["id"] or str(rec["number"]) for rec, _ in entries)),
              file=sys.stderr)
    return html_text.replace(ANN_SENTINEL, panel + _ann_all_html(records) + bubbles)


def render_index(manifest: dict, by_id: dict, css_rel: str, index_dir: str, root: str,
                 design: dict | None = None) -> str:
    product = manifest.get("product", {})
    design = design or {}
    modules = {m.get("id"): m for m in manifest.get("modules", []) if isinstance(m, dict)}
    items = []
    for m in manifest.get("modules", []):
        if not isinstance(m, dict):
            continue
        items.append('<h3>%s</h3><ul>' % esc(m.get("title", m.get("id"))))
        for p in manifest.get("pages", []):
            if isinstance(p, dict) and p.get("moduleId") == m.get("id") \
                    and p.get("nav") == "standalone":
                href = os.path.relpath(os.path.join(root, p["file"]),
                                       os.path.join(root, index_dir)).replace(os.sep, "/")
                items.append('<li><a href="%s" data-nav="%s">%s</a>'
                             '<span style="color:#8b949e;font-size:12px"> · %s</span></li>'
                             % (esc(href), esc(p["id"]),
                                esc(p.get("title", p["id"])), esc(p["id"])))
        items.append("</ul>")
    # 设计基线展示页：无论是否接上设计文档都在（缺文档时是骨架），
    # 索引要能进得去，否则两个展示页就是孤儿
    index_file = os.path.join(index_dir, "index.html")
    design_items = []
    for key, title, hint in (
            ("components_page", "组件 × 状态", "逐组件逐状态"),
            ("states_page", "跨模块五状态",
             "empty/loading/error/disabled/permission-denied")):
        rel = design.get(key)
        if rel:
            # 用 href_between 而不是 rel_href：index_file 是绝对路径、rel 是
            # **相对 root** 的声明值，rel_href 拿这对混口径的值算 relpath，
            # 结果随 cwd 变——cwd ≠ root 时就是死链（下一行的 spec_rel 一直
            # 用的是 href_between，同一段里两种写法，这里对齐）。
            design_items.append(
                '<li><a href="%s">%s</a>'
                '<span style="color:#8b949e;font-size:12px"> · %s</span></li>'
                % (esc(href_between(root, index_file, rel)), esc(title), esc(hint)))
    if design.get("spec_rel"):
        design_items.append('<li><a href="%s">DESIGN.md</a>'
                            '<span style="color:#8b949e;font-size:12px"> · 三层 token 基线</span></li>'
                            % esc(href_between(root, index_file, design["spec_rel"])))
    design_section = ('<h3>设计基线</h3><ul>%s</ul>' % "".join(design_items)) \
        if design_items else ""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>%(product)s · 原型索引</title>
<link rel="stylesheet" href="%(css)s">
</head>
<body>
<div class="jf-index">
  <h1>%(product)s 原型索引</h1>
  <p style="color:#57606a">只列导航页（standalone）；子流程页从宿主页的「从属与跳转」区进入。</p>
  %(items)s
  %(design_section)s
</div>
</body>
</html>
""" % {"product": esc(product.get("name", "原型")), "css": esc(css_rel),
       "items": "\n  ".join(items), "design_section": design_section}


# --------------------------------------------------------------------------- #
# 客户演示档控制台（console.html）
# --------------------------------------------------------------------------- #

def render_console(manifest: dict, by_id: dict, css_rel: str, root: str,
                   console_rel: str) -> str:
    """演示控制台：模块 → 场景 → 步骤，每条步骤链到目标页并可带 `?state=`。

    console_rel 是**相对 root** 的自身路径（不是目录）——链接一律走
    href_between 先 join(root) 再算相对路径。rel_href 拿两个声明值直接
    relpath，只在同一棵目录树里凑巧成立；控制台与页面不在同一层，用错必翻车
    （render_index 的设计基线链接就栽在这上面）。

    manifest 未声明 scenes[] 时退化为「模块 → 页面清单」（加强版索引）并报 WARN
    ——与套件「没配执行者就走内置路径」的既有约定一致。
    """
    product = manifest.get("product", {})
    scenes = manifest.get("scenes") or []
    if not scenes:
        print("WARN 演示档：manifest 未声明 scenes[]，console.html 退化为"
              "「模块 → 页面清单」（加强版索引），不按场景串场", file=sys.stderr)

    by_module: dict = {}
    for sc in scenes:
        if isinstance(sc, dict):
            by_module.setdefault(sc.get("moduleId"), []).append(sc)

    def page_link(p: dict, label: str, state: str) -> str:
        href = href_between(root, console_rel, p["file"])
        if state and state != "default":
            # 只在这里拼原值，转义统一交给下面那次 esc——先 esc 再拼会把
            # `&` 之类转义两遍（`&amp;` 二次转义成 `&amp;amp;`）。
            href += "?state=%s" % state
        return '<a href="%s" data-nav="%s">%s</a>' % (esc(href), esc(p["id"]), esc(label))

    blocks = []
    for m in manifest.get("modules", []):
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        blocks.append('<h2>%s</h2>' % esc(m.get("title", mid)))
        mod_scenes = by_module.get(mid, [])
        if not mod_scenes:
            # 该模块没有场景：列页面清单，控制台至少还能当索引用。
            # 只出页面标题——页 ID 是工程标注，不进给客户看的树。
            rows = [page_link(p, p.get("title", p["id"]), "")
                    for p in manifest.get("pages", [])
                    if isinstance(p, dict) and p.get("moduleId") == mid and p.get("file")]
            blocks.append("<ul>%s</ul>" % "".join("<li>%s</li>" % r for r in rows)
                          if rows else '<p class="jf-doc-note">该模块暂无页面。</p>')
            continue
        for sc in mod_scenes:
            flow = ('<span class="jf-doc-note"> · %s</span>' % esc(sc["flow"])) \
                if sc.get("flow") else ""
            blocks.append('<h3>%s%s</h3>' % (esc(sc.get("title", sc.get("id"))), flow))
            steps = []
            for step in sc.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                p = by_id.get(step.get("pageId"))
                if not p or not p.get("file"):
                    continue
                state = step.get("state") or "default"
                label = step.get("label") or p.get("title", p["id"])
                # 状态标签进链接文字：同页多状态的两步在控制台上才分得开。
                # 用 STATE_LABELS 的中文标签而不是裸 token（empty/error）——
                # 控制台是**给客户看的**入口页，工程 token 是 PM chrome；
                # 裸 token 只留在 href 的 ?state=（那是跳转协议，不是文案）。
                suffix = ("　<code>%s</code>" % esc(STATE_LABELS.get(state, state))) \
                    if state != "default" else ""
                steps.append("<li>%s%s</li>" % (page_link(p, label, state), suffix))
            blocks.append("<ol>%s</ol>" % "".join(steps)
                          if steps else '<p class="jf-doc-note">该场景暂无可用步骤。</p>')

    if not blocks:
        blocks.append('<p class="jf-doc-note">manifest 里没有可演示的模块。</p>')

    body = ('<p class="jf-doc-note">按业务场景串场：点一条步骤，直接落到目标页面的'
            '对应状态。</p>'
            + "".join(blocks))
    return display_shell(product.get("name", "原型"), "客户演示控制台", css_rel, body,
                         kind="演示控制台")


# --------------------------------------------------------------------------- #
# 设计基线展示页（components.html / states.html）
# --------------------------------------------------------------------------- #

# 展示页自带样式：一律 var(--jf-x, 兜底) 取值，产品自带 tokens.css 缺哪个变量
# 都能看；不写死颜色，避免和产品色板打架。
DISPLAY_CSS = """*{box-sizing:border-box}
body{margin:0;background:var(--jf-bg,#f7f8fa);color:var(--jf-text,#1f2328);
  font:14px/1.6 var(--jf-font,-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif)}
.jf-doc{max-width:1080px;margin:0 auto;padding:var(--jf-space-6,32px) var(--jf-space-5,24px)}
.jf-doc h1{font-size:22px;margin:0 0 var(--jf-space-2,8px)}
.jf-doc h2{font-size:16px;margin:var(--jf-space-6,32px) 0 var(--jf-space-3,12px);
  padding-bottom:var(--jf-space-2,8px);border-bottom:1px solid var(--jf-border,#e3e6ea)}
.jf-doc a{color:var(--jf-accent,#33557d)}
.jf-doc-note{color:var(--jf-text-weak,#57606a);font-size:13px;margin:0 0 var(--jf-space-4,16px)}
.jf-doc-note code{background:var(--jf-accent-weak,#edf2f6);padding:1px 5px;border-radius:3px}
.jf-demo-tiles{display:grid;gap:var(--jf-space-3,12px);
  grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}
.jf-demo-tile{background:var(--jf-surface,#fff);border:1px solid var(--jf-border,#e3e6ea);
  border-radius:var(--jf-radius,6px);padding:var(--jf-space-3,12px)}
.jf-demo-tile-label{font-size:12px;color:var(--jf-text-faint,#8b949e);margin-bottom:6px}
.jf-demo-specimen{min-height:52px;display:flex;flex-direction:column;gap:6px;justify-content:center}
.jf-demo-btn{display:inline-block;align-self:flex-start;padding:5px 12px;border-radius:var(--jf-radius,6px);
  background:var(--jf-btn-bg,var(--jf-accent,#33557d));color:var(--jf-btn-fg,#fff);font-size:13px}
.jf-demo-note{font-size:12px;color:var(--jf-text-weak,#57606a)}
.jf-demo-error{border:1px solid var(--jf-danger,#c0392b);background:var(--jf-danger-weak,#fdf0ee);
  color:var(--jf-danger,#c0392b);border-radius:var(--jf-radius,6px);padding:5px 10px;font-size:13px}
.jf-skel{height:10px;border-radius:4px;background:var(--jf-border,#e3e6ea)}
.jf-demo-tile[data-demo-state="hover"] .jf-demo-btn{background:var(--jf-btn-bg-hover,var(--jf-accent-weak,#edf2f6));
  color:var(--jf-accent,#33557d);outline:1px solid var(--jf-accent-line,#c9d5e0)}
.jf-demo-tile[data-demo-state="active"] .jf-demo-btn{filter:brightness(.88);transform:translateY(1px)}
.jf-demo-tile[data-demo-state="disabled"] .jf-demo-btn{opacity:.45;cursor:not-allowed}
.jf-demo-tile[data-demo-state="disabled"] .jf-demo-specimen{opacity:.7}
.jf-demo-tile[data-demo-state="permission-denied"] .jf-demo-specimen{opacity:.7}
/* 容器示意：画子部件，不画容器没有的主操作按钮 */
.jf-demo-shell{display:flex;flex-direction:column;gap:5px;width:132px}
.jf-demo-nav{height:8px;border-radius:3px;background:var(--jf-accent-line,#c7d7fe)}
.jf-demo-row{height:8px;border-radius:3px;background:var(--jf-skeleton,#eceff2)}
.jf-demo-row.is-lead{width:64%}
.jf-demo-tile[data-demo-state="hover"] .jf-demo-row{background:var(--jf-border,#e3e6ea)}
.jf-demo-tile[data-demo-state="active"] .jf-demo-row.is-lead{background:var(--jf-accent-weak,#eff4ff);
  outline:1px solid var(--jf-accent-line,#c7d7fe)}
.jf-demo-tile[data-demo-state="disabled"] .jf-demo-shell{opacity:.45}
.jf-demo-kind{font-size:12px;color:var(--jf-text-faint,#8b949e)}
.jf-demo-landing{margin:var(--jf-space-2,8px) 0 0;padding-left:var(--jf-space-4,16px);
  font-size:13px;color:var(--jf-text-weak,#57606a)}
.jf-demo-meta{font-size:12px;color:var(--jf-text-faint,#8b949e);margin-top:6px}
.jf-demo-cross{background:var(--jf-surface,#fff);border:1px solid var(--jf-border,#e3e6ea);
  border-radius:var(--jf-radius,6px);padding:var(--jf-space-4,16px);margin-bottom:var(--jf-space-3,12px)}
.jf-demo-cross h3{margin:0 0 var(--jf-space-2,8px);font-size:15px}
.jf-demo-cross dl{margin:0;display:grid;grid-template-columns:88px 1fr;gap:4px var(--jf-space-3,12px);font-size:13px}
.jf-demo-cross dt{color:var(--jf-text-faint,#8b949e)}
.jf-demo-cross dd{margin:0}
.jf-demo-undefined{border-left:3px solid var(--jf-danger,#c0392b);padding-left:var(--jf-space-2,8px)}
.jf-doc-nav a{margin-right:var(--jf-space-3,12px);font-size:13px}
"""


def container_specimen(state: str) -> str:
    """容器的状态示意：画它的子部件（导航条 / 内容行），不画它没有的主操作按钮。

    页面外壳哪来的「主操作」？给容器套用交互组件的示意件，
    图上就多出一个现实中不存在的控件——原型是拿给人对着评审的，不能这么编。
    状态落在哪个子部件上由表下的落点说明交代，这里只画出「有这几个部件」。
    """
    lead = "is-lead" if state == "active" else ""
    caption = {
        "default": "容器就位，子部件常态",
        "hover": "悬停落在子部件（见下方落点说明）",
        "active": "选中态落在子部件（见下方落点说明）",
        "disabled": "整体降透明度（见下方落点说明）",
    }.get(state, "")
    return ('<div class="jf-demo-shell">'
            '<span class="jf-demo-nav"></span>'
            '<span class="jf-demo-row is-lead"></span>'
            '<span class="jf-demo-row %s"></span>'
            '</div><span class="jf-demo-note">%s</span>'
            % (lead, esc(caption)))


def state_specimen(state: str, kind: str = "交互") -> str:
    """单个状态格里的示意件：够看出差异即可，具体造型以产品设计为准。

    按组件类型分派：容器没有自己的交互，套用交互组件的按钮示意会凭空造出控件。
    """
    if kind == "容器":
        return container_specimen(state)
    if state == "loading":
        return ('<div class="jf-skel" style="width:88%"></div>'
                '<div class="jf-skel" style="width:60%"></div>')
    if state == "empty":
        return '<div class="jf-demo-note">暂无数据（空态文案待与业务方确认）</div>'
    if state == "error":
        return '<div class="jf-demo-error">加载失败，请重试</div>'
    if state == "permission-denied":
        return '<div class="jf-demo-note">无访问权限（请联系管理员开通）</div>'
    if state == "disabled":
        return ('<span class="jf-demo-btn" aria-disabled="true">主操作</span>'
                '<span class="jf-demo-note">禁用：不可点，不响应 hover</span>')
    return '<span class="jf-demo-btn">主操作</span><span class="jf-demo-note">可点</span>'


def state_tile(component_id: str, state: str, kind: str = "交互") -> str:
    """一块「某组件的某状态」展位，data-demo-state 供 e2e 断言。"""
    return ('<div class="jf-demo-tile" data-demo-state="%s" data-component="%s" '
            'data-component-kind="%s">'
            '<div class="jf-demo-tile-label">%s</div>'
            '<div class="jf-demo-specimen">%s</div></div>'
            % (esc(state), esc(component_id), esc(kind),
               esc(STATE_LABELS.get(state, state)), state_specimen(state, kind)))


def display_shell(title: str, subtitle: str, css_rel: str, body: str,
                  kind: str = "设计基线") -> str:
    """展示页外壳：自带兜底样式，产品 tokens.css 在则叠加。

    kind 进 <title> 后缀——console.html 复用本外壳，写死「设计基线」会把标题
    拼成「XX · 演示控制台 · 设计基线」。
    """
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s · %(kind)s</title>
<link rel="stylesheet" href="%(css)s">
<style>%(style)s</style>
</head>
<body>
<div class="jf-doc">
  <h1>%(title)s</h1>
  <p class="jf-doc-note">%(subtitle)s</p>
  %(body)s
</div>
</body>
</html>
""" % {"title": esc(title), "subtitle": subtitle, "css": esc(css_rel),
       "style": DISPLAY_CSS, "body": body, "kind": esc(kind)}


def render_components_page(manifest: dict, design: dict, entries: list,
                           css_rel: str, index_href: str) -> str:
    if entries and entries[0]["from_doc"]:
        source = ('数据源：<code>%s</code>（组件×状态表；改设计请改该文件后重跑渲染）'
                  % esc(design.get("states_rel")))
    else:
        source = ('数据源：<code>manifest.components[]</code> 骨架——'
                  '未找到 <code>components-and-states.md</code>，四态为占位，'
                  '待 jf-design 补齐后重渲染')
    blocks = []
    for e in entries:
        is_container = e["kind"] == "容器"
        tiles = "".join(state_tile(e["id"], s, e["kind"]) for s in COMPONENT_STATES)
        tiles += "".join(state_tile(e["id"], s, e["kind"]) for s in e["extra"])
        meta = []
        if e["tokens"]:
            meta.append("引用 token：%s" % esc(e["tokens"]))
        if e["usedBy"]:
            meta.append("usedBy：%s" % esc(e["usedBy"]))
        # 容器没有自己的交互，四态的落点在子部件上——不能照抄
        # 「四态必须齐全」，那句话对容器是假的（容器本来就允许标 —）
        if is_container:
            states_note = ("；容器类，四态落在子部件上（见落点说明）")
        else:
            states_note = "；其他状态：%s" % esc("、".join(e["extra"])) if e["extra"] else ""
        landing = ""
        if is_container and e["note"]:
            # 落点说明是容器状态的唯一交代，必须进页面，不能只留在 Markdown 里
            landing = ('<p class="jf-demo-landing" data-container-note="%s">%s</p>'
                       % (esc(e["id"]), esc(e["note"])))
        blocks.append(
            '<h2 data-component-title="%s">%s <code>%s</code> '
            '<span class="jf-demo-kind">%s</span></h2>'
            '<p class="jf-doc-note">四态 default / hover / active / disabled%s</p>'
            '<div class="jf-demo-tiles">%s</div>%s'
            % (esc(e["id"]), esc(e["title"]), esc(e["id"]), esc(e["kind"]),
               states_note, tiles, landing)
            + ('<p class="jf-demo-meta">%s</p>' % " ｜ ".join(meta) if meta else ""))
    if not blocks:
        blocks.append('<div class="jf-demo-error">manifest.components[] 为空，'
                      '没有可展示的组件</div>')
    nav = ('<p class="jf-doc-nav"><a href="%s">← 原型索引</a>'
           '<a href="states.html">跨模块状态 →</a></p>' % esc(index_href))
    return display_shell("组件 × 状态", source, css_rel, nav + "".join(blocks))


def render_states_page(design: dict, entries: list, css_rel: str,
                       index_href: str) -> str:
    if any(e["defined"] for e in entries):
        source = ('数据源：<code>%s</code>（跨模块状态表）'
                  % esc(design.get("states_rel")))
    else:
        source = ('数据源：内置骨架——未找到 <code>components-and-states.md</code>，'
                  '五状态为占位，待 jf-design 补齐后重渲染')
    blocks = []
    for e in entries:
        rows = [("触发场景", e["scene"]), ("视觉表现", e["visual"]),
                ("文案口径", e["copy"]), ("落点组件", e["owner"])]
        dl = "".join("<dt>%s</dt><dd>%s</dd>" % (esc(k), esc(v) if v else "—")
                     for k, v in rows)
        cls = "jf-demo-cross" + ("" if e["defined"] else " jf-demo-undefined")
        flag = "" if e["defined"] else "（未定义，待补）"
        blocks.append(
            '<div class="%s" data-cross-state="%s">'
            '<h3>%s <code>%s</code>%s</h3>'
            '<div class="jf-demo-tiles" style="margin-bottom:12px">%s</div>'
            '<dl>%s</dl></div>'
            % (cls, esc(e["id"]), esc(STATE_LABELS.get(e["id"], e["id"])),
               esc(e["id"]), esc(flag), state_tile("cross", e["id"]), dl))
    nav = ('<p class="jf-doc-nav"><a href="%s">← 原型索引</a>'
           '<a href="components.html">组件×状态 →</a></p>' % esc(index_href))
    return display_shell("跨模块五状态", source, css_rel, nav + "".join(blocks))


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

def render(manifest: dict, root: str, out_dir: str | None = None,
           strict: bool = False, demo: bool = False) -> list[tuple[str, bool]]:
    """渲染全部产物，返回 [(路径, 是否复用产品自带文件)]。

    demo=True 走客户演示档：每页关掉标注层与 meta 行，并额外产出 console.html。
    """
    pages = [p for p in manifest.get("pages", []) if isinstance(p, dict)]
    by_id = {p["id"]: p for p in pages if p.get("id")}
    if not pages:
        raise SystemExit("manifest 中没有可渲染的 pages")

    design = resolve_design(manifest, root)
    if strict:
        for field, rel in design["missing"]:
            print("WARN 设计基线：design.%s 声明的文件不存在，已降级：%s" % (field, rel),
                  file=sys.stderr)
        if not design["declared"]:
            print("WARN 设计基线：manifest 未声明 design，"
                  "设计基线降级为内置单色规范", file=sys.stderr)
        elif not design["wired"]:
            print("WARN 设计基线：design.spec / design.states 均不可用，"
                  "页面不挂设计基线徽标", file=sys.stderr)

    # shared 目录：取页面目录的共同父级的 shared
    first_dir = os.path.dirname(pages[0]["file"]) or "."
    shared_dir = os.path.normpath(os.path.join(first_dir, "..", "shared"))

    # tokens：产品自带的存在就原样复用（绝不覆盖），否则写内置降级规范
    outputs: list[tuple[str, bool]] = []
    if design["tokens_rel"]:
        tokens_path = design["tokens_path"]
        outputs.append((tokens_path, True))
    else:
        tokens_path = os.path.join(root, shared_dir, "tokens.css")
        os.makedirs(os.path.dirname(tokens_path), exist_ok=True)
        with open(tokens_path, "w", encoding="utf-8") as f:
            f.write(TOKENS_CSS)
        outputs.append((tokens_path, False))

    if design["components_rel"]:
        components_path = design["components_path"]
        outputs.append((components_path, True))
    else:
        components_path = os.path.join(root, shared_dir, "components.js")
        os.makedirs(os.path.dirname(components_path), exist_ok=True)
        with open(components_path, "w", encoding="utf-8") as f:
            f.write(COMPONENTS_JS)
        outputs.append((components_path, False))

    # 展示页落在原型根（与 index.html 同处），先算出相对 root 的路径
    index_dir = prototypes_root(pages[0]["file"])
    components_page = os.path.relpath(
        os.path.join(root, index_dir, "components.html"), root).replace(os.sep, "/")
    states_page = os.path.relpath(
        os.path.join(root, index_dir, "states.html"), root).replace(os.sep, "/")
    design_ctx = dict(design, root=root,
                      components_page=components_page, states_page=states_page)

    for p in pages:
        if not p.get("file"):
            continue
        page_path = os.path.join(root, p["file"])
        os.makedirs(os.path.dirname(page_path) or ".", exist_ok=True)
        css_rel = os.path.relpath(tokens_path, os.path.dirname(page_path)).replace(os.sep, "/")
        js_rel = os.path.relpath(components_path, os.path.dirname(page_path)).replace(os.sep, "/")
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(render_page(manifest, p, by_id, css_rel, js_rel, design_ctx,
                                demo=demo))
        outputs.append((page_path, False))

    # 入口索引 + 两张设计基线展示页都是 **PM chrome**：它们写着「原型索引」
    # 「只列导航页（standalone）」「设计基线」、页 ID 和组件×状态矩阵，全是
    # 工程视角。演示档一律**不产出**——留着就是「藏起来」而不是「摘掉」，
    # 客户在目录里照样打得开。演示树的入口是 console.html。
    #
    # css_rel 挂在 index 目录上算（console 与它同层），所以先算、两边共用。
    css_rel = os.path.relpath(
        tokens_path, os.path.join(root, index_dir)).replace(os.sep, "/")
    if not demo:
        index_path = os.path.join(root, index_dir, "index.html")
        os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(render_index(manifest, by_id, css_rel, os.path.dirname(index_path),
                                 root, design_ctx))
        outputs.append((index_path, False))

        # 两个设计基线展示页：设计文档缺了也照生成（骨架可打开，不至于点了 404）
        for path, html_text in (
                (os.path.join(root, components_page),
                 render_components_page(manifest, design_ctx,
                                        component_entries(manifest, design_ctx), css_rel,
                                        "index.html")),
                (os.path.join(root, states_page),
                 render_states_page(design_ctx, cross_state_entries(design_ctx), css_rel,
                                    "index.html"))):
            with open(path, "w", encoding="utf-8") as f:
                f.write(html_text)
            outputs.append((path, False))

    # 客户演示档的控制台：与 index.html 同目录，css_rel 可直接复用（此刻它是
    # 相对 index 目录算的，两者同处一层）
    if demo:
        console_rel = os.path.relpath(
            os.path.join(root, index_dir, "console.html"), root).replace(os.sep, "/")
        with open(os.path.join(root, console_rel), "w", encoding="utf-8") as f:
            f.write(render_console(manifest, by_id, css_rel, root, console_rel))
        outputs.append((os.path.join(root, console_rel), False))

    return outputs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="从 manifest.json 生成可跳转的多页 HTML 原型")
    ap.add_argument("manifest")
    ap.add_argument("--root", default=None, help="输出根目录，默认 manifest 所在目录")
    ap.add_argument("--out", default=None, help="同 --root（兼容写法）")
    ap.add_argument("--strict", action="store_true",
                    help="把设计基线降级情况作为 WARN 打到 stderr（只提示不拦截，退出码仍为 0）")
    ap.add_argument("--demo", action="store_true",
                    help="客户演示档：整棵树不出 PM chrome（每页摘掉标注层与 meta 行，"
                         "且不产出 index.html / components.html / states.html），"
                         "另出 console.html（场景控制台）")
    args = ap.parse_args(argv)

    path = os.path.abspath(args.manifest)
    if not os.path.isfile(path):
        print("找不到 manifest：%s" % path, file=sys.stderr)
        return 2
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)

    root = os.path.abspath(args.out or args.root or os.path.dirname(path))
    os.makedirs(root, exist_ok=True)
    outputs = render(manifest, root, strict=args.strict, demo=args.demo)

    print("渲染完成，共 %d 个文件：" % len(outputs))
    for w, reused in outputs:
        print("  %s%s" % (os.path.relpath(w, root), "（复用产品自带）" if reused else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
