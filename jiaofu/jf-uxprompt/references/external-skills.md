# jf-uxprompt 执行外包登记表

> 登记本 skill 各块的**外部执行者**：候选 skill / 安装命令 / 输入 / 期望产出 / 门禁 / 降级方案。
> 调研依据：`research/jf-prd-skill-benchmark-report.md`（候选 C1 `ui-ux-pro-max`、C2 `impeccable`、A1 `interaction-prd`、D1 `html-style-generator`、D2 `cc-designer`）。
> 本文件是 `SKILL.md`「执行者 · 外部执行者（候选）」那节的落地清单。

三条纪律（对所有外包点一律适用）：

1. **外包不改变契约**：外部执行者产出的每一页照样要能被 `manifest` 解释、被 `--strict` 校验通过。谁生成的 HTML 不重要，能不能点通、能不能对回 manifest 才重要。
2. **Token 写死值不依赖外部**：元提示词里的 Token/视觉是**拷贝**进去的写死值，生成时不再回头读设计体系——所以设计体系挂了也不会让生成这一步失败。
3. **未安装即降级**：候选一个都没装时走内置渲染器，链路不阻塞。**降级是刻意约定，不是缺陷**（`--strict` 只提示不拦截）。

## 外包点一：Token / 视觉写死值的来源（Step 0「从设计体系写死拷贝」）

| 候选 skill | 安装命令 | 输入 | 期望产出 | 门禁 | 降级方案 |
|---|---|---|---|---|---|
| `ui-ux-pro-max:design-system`——按产品类型/行业生成成套三层 token（primitive → semantic → component） | Claude Code：`/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill` → `/plugin install ui-ux-pro-max@ui-ux-pro-max-skill`；或 CLI：`npm install -g ui-ux-pro-max-cli` 后 `uipro init --ai claude`（`--global` 装到 `~/.claude/skills/`）。生成（需 Python 3.x，仅标准库）：`python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<产品/行业关键词>" --design-system -p "<产品名>"`，加 `--persist` 落盘 `design-system/<slug>/MASTER.md`，`-f markdown` 出 Markdown | ②PRD 的产品定位 + ①MRD/访谈里的受众与语气 + `manifest.design` 的字段约定 | `DESIGN.md`（三层 token 契约）+ 由它派生的 `prototypes/shared/tokens.css`；semantic/component 层只引用上一层，不出现裸值 | `python3 products/jf-design/scripts/check_design.py <manifest>` G1–G8 全过（G1 三层齐备、G2 无裸 hex 越层、G6 排除项、G7 tokens.css 落地一致、G8 引用 token 可解析） | 走 jf-design 内置简洁单色规范：近白画布、近黑文字、发丝边框、小圆角、无渐变、强调色禁用 Tailwind 默认蓝紫。渲染器自带 `tokens.css`，无需任何外部 skill |
| `impeccable`（`/impeccable init`）——把持久产品真相写进 `PRODUCT.md`，**与 `DESIGN.md`（视觉方向）分离** | Claude Code：`/plugin marketplace add pbakaus/impeccable` → `/plugin` 里安装；或项目根跑 `npx impeccable install`。装完在会话里跑 `/impeccable init` | 项目现状 + ②PRD；只补「受众/目的/运行环境/约束/语气/证据」这些材料性缺口 | `PRODUCT.md`（产品真相），供元提示词的文案与语气引用；视觉方向仍归 `DESIGN.md` | 不改契约层门禁；`PRODUCT.md` 里的受众/语气被元提示词引用后，⑥内部评审的「文案完整」一项要能对回它 | 不装——产品真相从 ①MRD + ②PRD 直接摘，元提示词照样自包含 |

## 外包点二：准高保真生成（Step 0 元提示词 → Step 1 结构+视觉 → Step 2 文案+数据）

| 候选 skill | 安装命令 | 输入 | 期望产出 | 门禁 | 降级方案 |
|---|---|---|---|---|---|
| `html-style-generator`（Renais-Star）——需求 → 多页 HTML + 自检 | 安装方式未核实，以仓库 README 为准：`https://github.com/Renais-Star/html-style-generator` | 元提示词（PC 覆盖声明 + PB 禁止事项 + 写死 Token + 文案引用 CS + 数据引用 DD + 导航/状态指令） | 多页自包含 HTML：每页可独立打开、跳转可点、状态可切 | 渲染后过 `python3 products/jf-validate/scripts/validate_manifest.py <manifest> --strict`（退出码 0，文件存在性/链接一致性/标注锚点全过）；链接可达性用 `python3 tests/e2e/jf_contract_check.py <manifest>` | 内置渲染器：`python3 products/jf-uxprompt/scripts/render_manifest.py <manifest>` —— 按 `pages[].file` 落盘，同时出 `shared/tokens.css`、`shared/components.js`、`index.html`，以及 `components.html` / `states.html` 两个展示页（**后三张都是 PM 展示页，只随评审树产出**） |
| `cc-designer`（Openclaw-Metis）——`DESIGN.md` → 自包含 HTML | 安装方式未核实，以仓库 README 为准：`https://github.com/Openclaw-Metis/cc-designer` | `DESIGN.md` + `manifest.json` + 演示数据 | 自带完整视觉的多页 HTML | 同上 | 同上 |
| `impeccable`（`/impeccable shape`）——生成之前先规划 UX/UI（元提示词的上游） | 见外包点一 | ③IA 的 manifest + ⑤线框 + 设计体系 | UX/UI 规划稿 → 转写为每页元提示词的导航/状态指令段 | 同上 | 本 skill 按 ⑤线框的 PW 标注与 manifest 的 `relations[]` 自行写元提示词 |
| `interaction-prd` runtime（comeonzhj）——主参照底座（契约 + 门禁 + 标注） | `git clone https://github.com/comeonzhj/interaction-prd` → `npm install && npm run dev` | `interaction-prd.json` 契约（本链路上由 `manifest.json` 对应） | 可点击原型底座 + 客户标注气泡 | 它的硬约束照抄进本链路：原型 HTML 的 basename 必须等于页面 ID，`relations[].from/to` 必须引用存在的页面——两条都由 `validate_manifest.py` 执行 | 不装——契约层已由 jf-contract + jf-validate 自持，底座用内置渲染器顶 |

### 标注气泡由谁出

`manifest.annotations` 是评审的索引（⑦`jf-review` 逐条过），所以**气泡不是可选项**：
换执行者只会换气泡的样子，不会换掉「每条标注点得开、未落点的必须现形」这件事。

| 候选 | 标注气泡 |
|---|---|
| `interaction-prd` runtime | 自带（底座定位就是「可点击原型 + 客户标注气泡」）。样式随它，**落点仍按 manifest 的 `target`** ——`#id` / `[data-annotation-anchor=值]` 两种形式，禁 nth-child |
| `html-style-generator` | 不自带——元提示词里要显式带标注段（编号 + target + title + content），或渲染后由本 skill 按契约补挂 |
| `cc-designer` | 同上 |
| `impeccable`（`/impeccable shape`） | 不涉及——它在上游，只出规划稿 |
| **内置渲染器** | 三支判定：命中正文元素 / 命中骨架锚点 → 挂徽标；都不中 → 「评审标注 · 未落点」区 + stderr WARN。骨架锚点表见 `jf-contract/references/manifest-schema.md#annotations` |

无论谁出气泡，**关掉 JS 也要能读到标注全文**——评审现场断网、脚本报错都不该让标注消失。
具体形态：页面里要有一份**不依赖脚本**的静态清单（本 skill 用 `<details class="jf-ann-all">`），
收录**全部**标注的编号/标题/状态/正文，**包括已经落点的那些**（它们的正文否则只活在
`display:none` 的气泡里）。⚠️ 这条**门禁不查**（F4 只管自洽），换执行者后要人工确认一次。

## 外包点三：⑥内部评审（视觉准确 / 文案完整 / 数据正确三项，通过才给⑦）

| 候选 skill | 安装命令 | 输入 | 期望产出 | 门禁 | 降级方案 |
|---|---|---|---|---|---|
| `impeccable`（`/impeccable critique`）——UX 设计评审：层级、清晰度、情绪共鸣 | 见外包点一 | 生成的页面 + 元提示词 + `DESIGN.md` | 评审发现清单（按严重度）→ 回改页面或元提示词 | 结论必须回写：**发现问题要么改、要么在⑦汇报里显式带出**，不许静默丢弃 | 本 skill 自行做「视觉/文案/数据」三项评审，逐项对照元提示词与 DD |
| `impeccable`（`/impeccable audit`）——技术质量检查：无障碍 / 性能 / 响应式；随附 61 条确定性反模式检测 CLI | 见外包点一。CLI 用法：`npx impeccable detect src/`、`npx impeccable detect index.html`、`npx impeccable detect --json .` | 生成产物目录或单个 HTML | 技术问题清单（a11y / 性能 / 响应式 / AI 味反模式） | `npx impeccable detect --json <目标>` 退出码 **0 = 无主要问题、2 = 有主要问题、1 = 有目标扫不了**；退出码 1 不当通过处理 | 本 skill 按设计基线的排除项 + 三条硬要求自检：强调色不落 Tailwind 默认蓝紫、四态可切换、五状态有落点 |

### 演示档由谁出

演示档 = 评审树**减去 PM chrome**、**加上** `console.html`。换执行者只换样子，
不换这四件事：

| 事项 | 要求 |
|---|---|
| 每页 PM chrome | 标注徽标 / 未落点区 / 静态全览 / meta 行（含 4 类徽标）一律不出。**是整层不渲染，不是 `display:none`**——后者客户按 Ctrl+U 照样看得见 |
| 三张 PM 展示页 | `index.html` / `components.html` / `states.html` **整棵不产出**。它们是「页面上没有、目录里有」的那类泄漏——客户双击就打开，里面写着「原型索引」「只列导航页（standalone）」「设计基线」，还逐个列页 ID |
| 保留的交互 | 状态切换按钮、「从属与跳转」区、modal 浮层都留：演示要能当场切给客户看，不是静态截图 |
| `console.html` | 「模块 → 场景 → 步骤」三级；非 default 步链接带 `?state=`，脚本未加载时落 `default`。**不得链回 `index.html`**——演示树里它不存在，那是死链 |

外部执行者不实现演示档时，两条路：

1. **改它的产出**（推荐）——按上表摘 chrome + 补 `console.html`，两棵树同源同一份
   manifest，不会分叉。演示树的门禁是 `jf_contract_check.py <manifest> --root <演示目录>`
   加 `check_demo_separation.py <演示目录>`（后者不认执行者，谁产的都查）。
2. **用内置渲染器另出一棵**——`render_manifest.py <manifest> --demo --out <演示目录>`。
   注意这会**丢掉准高保真的文案/数据/视觉**（内置渲染器只出骨架），只适合先验证
   「场景串场成不成立」，不适合当最终客户交付物。

⚠️ **演示树不过 `validate_manifest.py --strict`，这是设计如此**：F4 问的是「每条标注
在页面上有没有落点」，而演示档按设计不渲染标注层。演示树的失败**只该差 F4 这一项**
（I1–I12 / F1–F3 全绿），链接可达性由 `--root` 那道门禁管，PM chrome 有没有摘干净由
`check_demo_separation.py` 管。别为了让它过 validate 而把标注层塞回去。

## 接入细则

**内置渲染器的设计基线行为**（外部执行者不必实现，但要知道本链路怎么退化）：

- `manifest.design.tokens` 指向的文件存在 → **直接复用产品自带的 `tokens.css`，绝不覆盖或重新生成**；`components` 同理。
- `manifest.design.spec` / `states` 指向的文件存在 → 每页 meta 行标注「设计基线：DESIGN.md」并链到 `components.html` / `states.html`；两个展示页按组件×状态（`components-and-states.md`）与跨模块五状态铺开。（`--demo` 整棵不产出这三张页，链接与页面一起去掉。）
- 声明了 `design` 但文件缺失 → 页面**不挂设计基线徽标**（宁可不标，也不给「已有设计基线」的假信号），展示页仍按 `manifest.components[]` 骨架生成，可打开；`--strict` 把降级情况作为 WARN 打到 stderr，**退出码仍为 0**。
- 完全没声明 `design` → 全部按内置单色规范跑通，端到端不阻塞。

**内置渲染器的标注落点行为**（换执行者时最容易漏掉的一段）：

- target 在页面里能找到（正文元素或骨架锚点）→ 徽标挂到该元素上，点得开气泡。
- 找不到 → 进「评审标注 · 未落点」区并向 stderr 报 WARN，列出未落点的标注 id。
  退出码仍为 0——**未落点不是渲染失败**，是「这条还没落到真实元素上」的实情。
- 未落点条目自己带锚点，所以门禁 F4 照样过。F4 判的是「渲染器输出与 manifest
  自洽」，判不了「是否落在真实业务元素上」——那个落差归 WARN 和 ⑦评审管。

**共同门禁**（无论谁执行都要跑）：

```bash
python3 products/jf-validate/scripts/validate_manifest.py <manifest> --strict
python3 tests/e2e/jf_contract_check.py <manifest>          # 链接可达性（脱离渲染器直接打开 .html 也能跳）
```
