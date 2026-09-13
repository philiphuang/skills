# jf-wireframe 执行外包登记表

> 登记本 skill 各块的**外部执行者**：候选 skill / 安装命令 / 输入 / 期望产出 / 门禁 / 降级方案。
> 调研依据：`research/jf-prd-skill-benchmark-report.md`（候选 C1 `nextlevelbuilder/ui-ux-pro-max-skill`、C2 `pbakaus/impeccable`、D2 `Openclaw-Metis/cc-designer`）。
> 本文件是 `SKILL.md`「项目适配 · 执行外包」那条的落地清单。

三条纪律（对所有外包点一律适用）：

1. **外包不改变契约**：线框可以别人画，但 `manifest.json` 的 `pages[].frame`（`route` / `modal`）、`components[]`、`states` 必须与表格一致并过校验。
2. **框架判定不外移**：`modal` vs 全幅 route 的判定在本 skill 的 PW 块定（判定规则见 `SKILL.md`），外包方只细化、不推翻。
3. **未安装即降级**：候选没装时本 skill 自行执行七块，链路不阻塞。

## 外包点一：EC → PW → SV/MS/DDR（线框与状态）

| 候选 skill | 安装命令 | 输入 | 期望产出 | 门禁 | 降级方案 |
|---|---|---|---|---|---|
| `impeccable`（`/impeccable shape`）——PW 之前的 UX/UI 规划：页面优先级、状态侧重、视觉文案重点 | Claude Code：`/plugin marketplace add pbakaus/impeccable` → `/plugin` 里安装；或项目根跑 `npx impeccable install`（`--providers=claude`、`--scope=project\|global`） | ③IA 的 `manifest.json` + ①用户旅程 + ②PRD + 设计基线（`DESIGN.md` / `components-and-states.md`） | 逐页 ASCII 线框（区域 ID + 导航/字段约束/状态触发三要素标注 + 框架标注）；`route` 页与 `modal` 页分别成稿 | PW 的框架标注必须与 `manifest.pages[].frame` 逐页一致（`modal` 页有 `hostPageId`，子流程页页头标宿主页与激活入口）；产物过 `python3 products/jf-validate/scripts/validate_manifest.py <manifest> --strict` | 本 skill 自行跑 EC 先行 → PW → SV/MS/DDR 并行 |
| `cc-designer`（Openclaw-Metis）——`DESIGN.md` → 自包含 HTML，线框直接出可点版本 | 安装方式未核实，以仓库 README 为准：`https://github.com/Openclaw-Metis/cc-designer` | 同上 + `DESIGN.md` | 自带样式的多页 HTML 线框 | 同上；且每页跳转必须是原生相对链接（`<a href="./<id>.html" data-nav="<id>">`），脱离生成工具也能点通 | 本 skill 出 ASCII 线框，需要可点版本时交⑥内置渲染器（见 jf-uxprompt 的登记表） |

## 外包点二：GC → CSM（组件抽取与状态矩阵）

组件清单在③IA 已定，本块只**补状态**、不增删组件。组件×状态的落地文件是 jf-design 的 `components-and-states.md`。

| 候选 skill | 安装命令 | 输入 | 期望产出 | 门禁 | 降级方案 |
|---|---|---|---|---|---|
| `ui-ux-pro-max:design-system`——按产品类型/行业生成成套设计系统（三层 token + 组件建议） | Claude Code：`/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill` → `/plugin install ui-ux-pro-max@ui-ux-pro-max-skill`；或 CLI：`npm install -g ui-ux-pro-max-cli` 后 `uipro init --ai claude`（`--global` 装到 `~/.claude/skills/`）。生成命令（需 Python 3.x，仅标准库）：`python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<产品/行业关键词>" --design-system -p "<产品名>"`，加 `--persist` 落盘 `design-system/<slug>/MASTER.md`，`-f markdown` 出 Markdown | `manifest.components[].id` + 产品类型/行业 + `DESIGN.md` 的产品基调 | GC 组件定义（Rule of Three：≥3 页重复）→ `components-and-states.md` 的「组件×状态」表：每组件四态 default/hover/active/disabled 齐全，id 列可追溯到 `manifest.components[].id`；CSM 矩阵：用户状态 × 组件状态 | `python3 products/jf-design/scripts/check_design.py <manifest>` G1–G8 全过——重点 G3（组件四态）、G4（跨模块五状态 empty/loading/error/disabled/permission-denied 齐全）、G5（id 可追溯） | 本 skill 自行抽 GC + 写 CSM；`DESIGN.md` 缺失时用内置简洁单色规范（`render_manifest.py` 自带 `tokens.css`），不阻塞 |

## 接入细则

**共同门禁**：

```bash
python3 products/jf-validate/scripts/validate_manifest.py <manifest> --strict   # 契约层
python3 products/jf-design/scripts/check_design.py <manifest>                   # 设计基线层（G1–G8）
```

**降级自检**：不装任何候选时，本 skill 的七块流程与上面「期望产出」完全同构；组件与状态只要落在 `manifest.components[].states` 和 `components-and-states.md` 两处且二者对齐，⑤这一步就算交付。
