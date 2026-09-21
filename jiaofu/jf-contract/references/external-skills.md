# jf-* 执行外包登记表（中央表）

> **套件级资产，落 `jf-contract`**：登记各拍内步骤的**外部执行者**——候选全名 / 安装来源 / 适配层输入 / 产出门禁 / 失败语义。
> **主键是步骤**，不是 skill：同一候选服务多个步骤时各记各的行；同一步骤换候选不换产物形状。
> 立场已定（[拍内执行链与外包调用契约 #151](https://github.com/philiphuang/skills-factory/issues/151)），本表不重议：**有机器门禁的才外包**；**外部调用失败即硬失败，不降级**。
> 候选事实以**上游仓库**为准（本机池子只是部分镜像）；核实依据 = [#150](https://github.com/philiphuang/skills-factory/issues/150) 调研 + [外包登记表 #170](https://github.com/philiphuang/skills-factory/issues/170) 对上游的复核。

## 三条通用纪律（对所有行一律适用）

1. **外包不改变契约**：外部执行者的产出照样过该行的产出门禁。jf-* 只管编排和门禁——只要产出过门禁，谁做的无所谓。
2. **配了就是前置要求，没配才走内置**：某步骤一个候选都没配 → 所属 skill 内置自执行（这是默认路径，不是异常）；配了哪个，哪个就是这个步骤的**前置要求**。
3. **失败即硬失败**：配置了的候选调用失败 → 停链打回，**不降级、不悄悄改走内置**。编排层管这条（步骤表看见失败就停下）——门禁量的是产物，看不见配没配执行者。

## 步骤索引

外包点集中在 **② 需求与设计（设计生产段，S1–S7）**；① 有一个访谈执行点（S0）；③ 客户评审、② 的规格段（FR→AC→API→RP→PP）、三基建暂无外包点——这些步骤的产物是契约本身、规格判断或评审判断，形状不被外部执行者完全决定（判据见 #151：产出形状被契约完全决定 ∧ 执行可脱离实时对话）。

| # | 步骤（主键） | 所属模块 | 候选 |
|---|---|---|---|
| S0 | 访谈执行（shaping 8 件套采集） | `jf-interview` | `write-a-prd` · `interview` · `grill-with-docs`（本仓库自带） |
| S1 | IA 四块 PS→LT→NM→FA | `jf-ia` | `impeccable` · `ux-strategy:information-architecture` · `design-research:card-sort-analysis` |
| S2 | 设计基线 5 块（基调→三层 token→组件×状态→展示页→门禁） | `jf-design` | `ui-ux-pro-max`（素材）· `ui-ux-pro-max:design-system`（token 落盘） |
| S3 | 线框 EC→PW→SV/MS/DDR | `jf-wireframe` | `impeccable` · `cc-designer` |
| S4 | 线框 GC→CSM | `jf-wireframe` | `ui-ux-pro-max` |
| S5 | 原型渲染 Step 0：Token/视觉写死值来源 | `jf-uxprompt` | `ui-ux-pro-max:design-system` · `impeccable`（PRODUCT.md） |
| S6 | 原型渲染 Step 1–2：准高保真生成 | `jf-uxprompt` | `html-style-generator` · `cc-designer` · `impeccable` · `interaction-prd` runtime |
| S7 | 原型渲染内部评审（视觉/文案/数据） | `jf-uxprompt` | `impeccable`（critique / audit） |

---

## S0 · 访谈执行：shaping 8 件套采集（`jf-interview`）

jf-* 保留节奏约束（3–5 问/带推荐答案/不问我能查的）与产物结构；外部执行者只换「谁主持」。

| 候选（全名） | 安装来源 | 适配层输入 | 产出门禁 | 失败语义 |
|---|---|---|---|---|
| `write-a-prd`（mattpocock，同源工程 skill 体系） | 安装方式未核实，以该仓库 README 为准 | ①MRD 摘要 / 一句话问题（00-intake）+ DR 待拍板项 | `shaping/` 8 件套（00-intake … 07-open-questions）→ `python3 products/jiaofu/jf-interview/scripts/check_shaping.py <shaping目录>` 退出码 0（G1–G7）；只产出一段聊天记录视为未完成 | 硬失败 |
| `interview`（MalekAG 追问库） | 安装方式未核实，以该仓库 README 为准 | 同上 | 同上 | 硬失败 |
| `grill-with-docs`（本仓库） | **自带**——`.claude/skills/`（工厂内注记，部署后不可用），有 codebase 时优先 | 同上 + 代码库 | 同上 | 硬失败 |

**降级方案**：一个都没配 → jf-interview 自行主持；最低限走 jf-mrd 自带采集流程。

---

## S1 · IA 四块：PS → LT → NM → FA（`jf-ia`）

产出 `manifest.json` 骨架（`modules[]` / `pages[]` / `relations[]`），是下游线框（jf-wireframe）与原型渲染（jf-uxprompt）的唯一输入。四块串行，**候选整体接手，不能只做一块**（card-sort 除外，它只喂 LT/NM 的表内容）。**只交文档表视为未完成**——IA 的产物是 manifest，不是漂亮的表格。

| 候选（全名） | 安装来源 | 适配层输入 | 产出门禁 | 失败语义 |
|---|---|---|---|---|
| `impeccable`（`/impeccable shape`）——写代码之前先规划 UX/UI，补 PRD 与页面之间那一环 | Claude Code：`/plugin marketplace add pbakaus/impeccable` → `/plugin` 里安装；或项目根 `npx impeccable install`（`--providers=claude`、`--scope=project\|global`）；升级 `npx impeccable update` | ②PRD（FR/AC/RP/PP）+ ①用户旅程；PS/LT/NM 表头作为输出模板 | UX/UI 规划稿由 jf-ia 转写为 PS/LT/NM 三张表并落 manifest → `python3 products/jiaofu/jf-validate/scripts/validate_manifest.py <manifest> --strict` 退出码 0（I1–I12 + F1–F4 全过，WARN 也计入失败） | 硬失败 |
| `ux-strategy:information-architecture`（marketplace `Owl-Listener/designer-skills`）——现成 IA 工作流 | `/plugin marketplace add Owl-Listener/designer-skills` → `/plugin` 里安装 `ux-strategy` 插件（以该仓库 README 为准） | 同上 | 站点地图 / 页面清单 / 导航层级 → 整表映射到 `pages[]`（`nav` / `hostPageId` / `frame` 三列不许留空或猜）→ 同上门禁 | 硬失败 |
| `design-research:card-sort-analysis`（同 marketplace）——LT/NM 两块的分组与命名单独外包 | 同上（装 `design-research` 插件） | ②PRD 功能清单（FR）+ 用户角色 | 卡片分组结果（分组名 + 归属卡片 + 分歧点）只决定 LT/NM 表内容，分歧点单列不自行裁决；**不豁免 manifest 校验** → 同上门禁 | 硬失败 |

> 命名校正（#170）：旧表把这条写作 `card-sorting`——上游实名是 `design-research:card-sort-analysis`（该 marketplace 含 9 个插件，`card-sort-analysis` 在 `design-research` 下）。

**外部产出 → manifest 转写映射**（外包方交表格时的转写入口）：

| 外部产出 | manifest 落点 | 关键判定 |
|---|---|---|
| 页面清单 / 站点地图 | `pages[]` | `nav`：可独立路由 → `standalone`；只在宿主页上下文中出现 → `sub-flow`（必须带 `hostPageId`） |
| 导航层级 / 分组 | `modules[]` + `pages[].moduleId` | 侧边导航只列 `standalone` 页，分组即 module |
| 跳转表 | `relations[]` | `type`：`route` / `modal` / `external`；`semantic`：`drill` / `back` / `rel` / `activate` |
| 组件清单 | `components[]` | 只登记 id 与 usedBy，**状态在 jf-design 的 `components-and-states.md` 里补齐**，IA 不增删组件 |

**降级自检**：不装任何候选时，jf-ia 的四块流程与「期望产出」完全同构——外包只换执行者，不换产物形状。

---

## S2 · 设计基线 5 块（`jf-design`）

`ui-ux-pro-max` 插件含 7 个 skill（banner-design / brand / design / design-system / slides / ui-styling / ui-ux-pro-max；本机池子只镜像了顶层）。与设计基线相关的**两个入口各管一段，别混**：

| 入口 | 是什么 | 产物 |
|---|---|---|
| `ui-ux-pro-max`（插件顶层 skill） | 本地设计情报库 + `search.py` 检索；`--design-system` 是它的**模式旗标** | `design-system/<slug>/MASTER.md`（设计系统文档 + 组件建议）——**素材生成** |
| `ui-ux-pro-max:design-system`（插件子 skill） | 三层 token 架构（primitive→semantic→component）+ `generate-tokens.cjs` | `tokens.css`——**token 落盘** |

> **理顺记录（#170）**：旧登记表把候选写成 `ui-ux-pro-max:design-system`（子 skill），命令却给顶层 skill 的 `search.py --design-system`——命令与 skill 对不上。中央表按「**素材归顶层、token 落盘归子 skill**」拆开登记，下面两行各配各的命令。

| 候选（全名） | 安装来源 | 适配层输入 | 产出门禁 | 失败语义 |
|---|---|---|---|---|
| `ui-ux-pro-max`（`--design-system` 模式） | Claude Code：`/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill` → `/plugin install ui-ux-pro-max@ui-ux-pro-max-skill`；或 CLI：`npm install -g ui-ux-pro-max-cli` 后 `uipro init --ai claude`（`--global` 装 `~/.claude/skills/`）。生成命令（需 Python 3.x，仅标准库）：`python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<产品/行业关键词>" --design-system -p "<产品名>"`，`--persist` 落盘 MASTER.md，`-f markdown` 出 Markdown | ②PRD 产品定位 + ①MRD/访谈的受众与语气 + `manifest.design` 的字段约定 | 基调素材与组件建议（MASTER.md）——供基调段与组件×状态段取材，由 jf-design 收编进 `DESIGN.md`。⚠️ `--persist` 前先查 MASTER.md 是否已存在：存在则跳过不覆盖，除非显式 `--force`（别静默丢弃已拍板的决策） | 素材被采纳进 DESIGN.md 后：`python3 products/jiaofu/jf-design/scripts/check_design.py <manifest>` G1–G8 全过——重点 G6（排除项） | 硬失败 |
| `ui-ux-pro-max:design-system` | 同上（同一插件） | `DESIGN.md` 的三层 token 约定（或 `tokens.json` 配置） | `node <skill 目录>/scripts/generate-tokens.cjs --config tokens.json -o tokens.css` 产 `tokens.css`（需 Node）；semantic/component 层只引用上一层，不出裸值 | 同上门禁——重点 G1（三层齐备）/ G2（无裸值越层）/ G7（tokens.css 落地一致）/ G8（引用可解析） | 硬失败 |

**降级方案**：两个都不装 → jf-design 内置简洁单色规范（近白画布、近黑文字、发丝边框、小圆角、无渐变、强调色禁用 Tailwind 默认蓝紫；渲染器自带 `tokens.css`）。

---

## S3 · 线框 EC→PW→SV/MS/DDR（`jf-wireframe`）

**框架判定不外移**：modal vs 全幅 route 在 PW 块定（判定规则见 jf-wireframe SKILL.md），外包方只细化、不推翻。组件清单在 IA 已定。

| 候选（全名） | 安装来源 | 适配层输入 | 产出门禁 | 失败语义 |
|---|---|---|---|---|
| `impeccable`（`/impeccable shape`）——PW 之前的 UX/UI 规划：页面优先级、状态侧重、视觉文案重点 | 同 S1 的 impeccable 安装来源 | IA（jf-ia）的 `manifest.json` + ①用户旅程 + ②PRD + 设计基线（`DESIGN.md` / `components-and-states.md`） | 逐页 ASCII 线框（区域 ID + 导航/字段约束/状态触发三要素标注 + 框架标注）；`route` 页与 `modal` 页分别成稿；PW 的框架标注与 `manifest.pages[].frame` 逐页一致（`modal` 页有 `hostPageId`，子流程页页头标宿主页与激活入口）→ `validate_manifest.py --strict` | 硬失败 |
| `cc-designer`（Openclaw-Metis）——`DESIGN.md` → 自包含 HTML，线框直接出可点版本 | 安装方式未核实，以仓库 README 为准：<https://github.com/Openclaw-Metis/cc-designer> | 同上 + `DESIGN.md` | 自带样式的多页 HTML 线框；每页跳转必须是原生相对链接（`<a href="./<id>.html" data-nav="<id>">`），脱离生成工具也能点通 → 同上门禁 | 硬失败 |

**降级方案**：不装 → jf-wireframe 自行跑 EC 先行 → PW → SV/MS/DDR 并行（ASCII 线框）；要可点版本时交 jf-uxprompt 内置渲染器（见 S6）。

---

## S4 · 线框 GC→CSM（`jf-wireframe`）

组件清单在 IA 已定，本步骤只**补状态、不增删组件**；组件×状态的落地文件是 jf-design 的 `components-and-states.md`。

| 候选（全名） | 安装来源 | 适配层输入 | 产出门禁 | 失败语义 |
|---|---|---|---|---|
| `ui-ux-pro-max`（`--design-system` 模式，取组件建议部分） | 同 S2 的安装来源与生成命令 | `manifest.components[].id` + 产品类型/行业 + `DESIGN.md` 的产品基调 | GC 组件定义（Rule of Three：≥3 页重复才提取）→ `components-and-states.md` 的组件×状态表：每组件四态 default/hover/active/disabled 齐全，id 列可追溯到 `manifest.components[].id`；CSM 矩阵：用户状态 × 组件状态 | `check_design.py` G1–G8 全过——重点 G3（组件四态）/ G4（跨模块五状态 empty/loading/error/disabled/permission-denied）/ G5（id 可追溯） | 硬失败 |

> 命名校正（#170）：旧表此行候选写作 `ui-ux-pro-max:design-system`——按 S2 的理顺，组件建议素材来自**顶层** skill 的 `--design-system` 模式，此处更正。

**降级方案**：不装 → jf-wireframe 自行抽 GC + 写 CSM；`DESIGN.md` 缺失时用内置简洁单色规范，不阻塞。

---

## S5 · 原型渲染 Step 0：Token/视觉写死值来源（`jf-uxprompt`）

| 候选（全名） | 安装来源 | 适配层输入 | 产出门禁 | 失败语义 |
|---|---|---|---|---|
| `ui-ux-pro-max:design-system`（三层 token 落盘） | 同 S2 的安装来源 | ②PRD 产品定位 + ①MRD/访谈的受众与语气 + `manifest.design` 字段约定 | `tokens.css`（`generate-tokens.cjs`）+ 三层 token 素材，由本链路收编为 `DESIGN.md` 契约；semantic/component 层只引用上一层 | `check_design.py` G1–G8（G1/G2/G6/G7/G8） | 硬失败 |
| `impeccable`（`/impeccable init`）——把持久产品真相写进 `PRODUCT.md`，与 `DESIGN.md`（视觉方向）分离 | 同 S1 的 impeccable 安装来源；装完在会话里跑 `/impeccable init` | 项目现状 + ②PRD；只补「受众/目的/运行环境/约束/语气/证据」这些材料性缺口 | `PRODUCT.md` 供元提示词的文案与语气引用；视觉方向仍归 `DESIGN.md`；被引用后 S7 的「文案完整」一项要能对回它（人工核） | 硬失败 |

**Token/视觉是拷贝进元提示词的写死值**——生成时不再回头读设计体系，所以设计体系挂了不会让 S6 的生成失败（这是写死值的性质，不是本步骤的降级口子）。

**降级方案**：一个都不装 → 走 jf-design 内置简洁单色规范（同 S2）；产品真相从 ①MRD + ②PRD 直接摘，元提示词照样自包含。

---

## S6 · 原型渲染 Step 1–2：准高保真生成（`jf-uxprompt`）

每页一份自包含元提示词（PC 覆盖声明 + PB 禁止事项 + 写死 Token + 文案引用 CS + 数据引用 DD + 导航/状态指令），两步生成（结构+视觉 → 文案+数据）。**执行者只决定「谁写 HTML」，不决定「HTML 长什么样」**——导航树、页面框架、跳转协议、标注气泡协议由 manifest 与 jf-uxprompt 的渲染规则定死；外部产出与内置产出过同一套门禁，一视同仁。

| 候选（全名） | 安装来源 | 适配层输入 | 产出门禁 | 失败语义 |
|---|---|---|---|---|
| `html-style-generator`（Renais-Star）——需求 → 多页 HTML + 自检 | 安装方式未核实，以仓库 README 为准：<https://github.com/Renais-Star/html-style-generator> | 元提示词（PC + PB + 写死 Token + CS/DD 引用 + 导航/状态指令） | 多页自包含 HTML：每页可独立打开、跳转可点、状态可切 → `validate_manifest.py --strict` 退出码 0 + `python3 tests/e2e/jf_contract_check.py <manifest>`（链接可达性） | 硬失败 |
| `cc-designer`（Openclaw-Metis） | 同 S3 | `DESIGN.md` + `manifest.json` + 演示数据 | 自带完整视觉的多页 HTML → 同上门禁 | 硬失败 |
| `impeccable`（`/impeccable shape`）——生成之前的 UX/UI 规划（元提示词的上游） | 同 S1 | IA（jf-ia）的 manifest + 线框（jf-wireframe）+ 设计体系 | UX/UI 规划稿 → 转写为每页元提示词的导航/状态指令段 → 同上门禁 | 硬失败 |
| `interaction-prd` runtime（comeonzhj）——主参照底座（契约 + 门禁 + 标注） | `git clone https://github.com/comeonzhj/interaction-prd` → `npm install && npm run dev` | `manifest.json` 契约——**本链路不产出 `interaction-prd.json`**：我们那份契约叫 manifest（定义见 jf-contract），执行者按它驱动 | 可点击原型底座 + 客户标注气泡；它的硬约束照抄进本链路：原型 HTML 的 basename 必须等于页面 ID、`relations[].from/to` 必须引用存在的页面——两条都由 `validate_manifest.py` 执行 → 同上门禁 | 硬失败 |

**降级方案**：一个都不装 → 内置渲染器：`python3 products/jiaofu/jf-uxprompt/scripts/render_manifest.py <manifest>`——按 `pages[].file` 落盘，同时出 `shared/tokens.css`、`shared/components.js`、`index.html` 与 `components.html` / `states.html` 两个展示页（**后三张是 PM 展示页，只随评审树产出**）。内置渲染器的完整行为（design 块解析、降级口径）见 jf-uxprompt SKILL.md「内置渲染器」。

### 标注气泡由谁出（S6 附则）

`manifest.annotations` 是评审的索引（③ 的 `jf-review` 逐条过），所以**气泡不是可选项**：换执行者只会换气泡的样子，不会换掉「每条标注点得开、未落点的必须现形」这件事。气泡协议权威定义见 `jf-contract/references/manifest-schema.md#annotations`。

| 候选 | 标注气泡 |
|---|---|
| `interaction-prd` runtime | 自带（底座定位就是「可点击原型 + 客户标注气泡」）。样式随它，**落点仍按 manifest 的 `target`**——`#id` / `[data-annotation-anchor=值]` 两种形式，禁 nth-child |
| `html-style-generator` | 不自带——元提示词里要显式带标注段（编号 + target + title + content），或渲染后由 jf-uxprompt 按契约补挂 |
| `cc-designer` | 同上 |
| `impeccable`（`/impeccable shape`） | 不涉及——它在上游，只出规划稿 |
| 内置渲染器 | 三支判定：命中正文元素 / 命中骨架锚点 → 挂徽标；都不中 → 「评审标注 · 未落点」区 + stderr WARN |

无论谁出气泡，**关掉 JS 也要能读到标注全文**——页面里要有一份不依赖脚本的静态清单（`<details class="jf-ann-all">`），收录**全部**标注的编号/标题/状态/正文（含已落点条目——它们的正文否则只活在 `display:none` 的气泡里）。⚠️ 这条**门禁不查**（F4 只管自洽），换执行者后要人工确认一次。

### 演示档由谁出（S6 附则）

演示档 = 评审树**减 PM chrome**、**加 `console.html`**（四件事清单与机器检查 A1–A6 见 jf-uxprompt SKILL.md「演示档纪律」）。外部执行者不实现演示档时，两条路：

1. **改它的产出**（推荐）——按清单摘 chrome + 补 `console.html`，两棵树同源同一份 manifest，不会分叉。演示树门禁 = `jf_contract_check.py <manifest> --root <演示目录>` + `check_demo_separation.py <演示目录>`（后者不认执行者，谁产的都查）。
2. **内置渲染器另出一棵**——`render_manifest.py <manifest> --demo --out <演示目录>`。注意这会**丢掉准高保真的文案/数据/视觉**（内置渲染器只出骨架），只适合先验证「场景串场成不成立」，不适合当最终客户交付物。

演示树**不过 `validate_manifest.py --strict`，这是设计如此**（只差 F4 一项；口径见 jf-uxprompt SKILL.md「演示档过哪道门禁」）。

---

## S7 · 原型渲染内部评审：视觉准确 / 文案完整 / 数据正确（`jf-uxprompt`）

三项通过才给 ③ 设计评审。

| 候选（全名） | 安装来源 | 适配层输入 | 产出门禁 | 失败语义 |
|---|---|---|---|---|
| `impeccable`（`/impeccable critique`）——UX 设计评审：层级、清晰度、情绪共鸣 | 同 S1 的 impeccable 安装来源 | 生成的页面 + 元提示词 + `DESIGN.md` | 评审发现清单（按严重度）→ 回改页面或元提示词；**结论必须回写：发现问题要么改、要么在 ③ 评审汇报里显式带出，不许静默丢弃** | 结论回写（人工核） | 硬失败 |
| `impeccable`（`/impeccable audit`）——技术质量检查：无障碍 / 性能 / 响应式；随附 61 条确定性反模式检测 CLI | 同上。CLI 用法：`npx impeccable detect src/`、`npx impeccable detect index.html`、`npx impeccable detect --json .` | 生成产物目录或单个 HTML | 技术问题清单（a11y / 性能 / 响应式 / AI 味反模式）；CLI 退出码 **0 = 无主要问题、2 = 有主要问题、1 = 目标扫不了**——退出码 1 不当通过处理 | 退出码判（见左） | 硬失败 |

**降级方案**：不装 → jf-uxprompt 自行做三项评审（视觉对照 DESIGN.md、文案对照元提示词与 `PRODUCT.md`、数据对照 DD）；audit 的替代 = 按设计基线排除项 + 三条硬要求自检：强调色不落 Tailwind 默认蓝紫、四态可切换、五状态有落点。

---

## 维护口径

- 各 skill 的执行外包条目（「项目适配 · 执行外包」或专门小节）一律指到本表，**不再各自维护登记表**；新增外包步骤先过 #151 的判据（产出形状被契约完全决定 ∧ 执行可脱离实时对话 ∧ 有机器门禁），过判据才上表。
- 安装来源标注「未核实」的行，接入前以该仓库 README 为准，核实后回写本表。
- 候选的名字、产物、CLI 面以**上游仓库**为准；本机池子只是部分镜像，池中无 ≠ 上游无。
