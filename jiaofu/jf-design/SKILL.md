---
name: jf-design
description: 交付·设计基线——三层token+组件×状态成为一等产物，jf-ia之后、jf-wireframe之前定稿。触发：设计基线、DESIGN.md、token、组件状态、视觉规范、设计体系。
---

# 设计基线

设计基线（token + 公共组件）是 jf-* 链路上的**独立一等步骤**：在 jf-ia 产出 manifest 之后、
jf-wireframe 画第一页之前定稿。先定全套 token 与组件状态，后面每一页引用同一套基线——
而不是画到第 5 页才发现按钮四种圆角、表格三种行高。

时间点为什么必须提前：靠 Rule of Three（≥3 页重复才抽）事后涌现太晚——前几页已经各写各的样式，
后面抽出来的公共组件也回不去改前面。结果客户评审时注意力全跑到视觉不一致上，而不是业务规则。

## 入口纪律

**正常路径**：由 `jf-prd` 在第 5 步调用。
**独立路径**：用户显式指名时可直接调用——此时先走 `jf-router` 判跨拍。

**典型误入**：
- 想「画页面线框」→ `jf-wireframe`（本 skill 是它的上游基线）
- 想「从 manifest 渲染 HTML」→ `jf-uxprompt`
- 想「校验页面跳转契约」→ `jf-validate`

## 输入与产物

输入：jf-ia 产出的 `manifest.json`（`modules[]` / `pages[]` / `components[]` 骨架）。

产物与登记路径（`manifest.design`，相对 manifest 所在目录）：

| 产物 | 字段 | 说明 |
|---|---|---|
| `DESIGN.md` | `design.spec` | 三层 token 契约，`tokens.css` 的真相源 |
| `components-and-states.md` | `design.states` | 组件×状态契约 |
| `prototypes/shared/tokens.css` | `design.tokens` | 由 DESIGN.md 派生的落地 CSS（同源） |
| `prototypes/components.html` / `states.html` | —（渲染器生成） | 评审展示页，供客户一眼看全套 |

## 5 块生成流程

```
jf-ia 的 manifest（pages/components 骨架）
    ↓
1. 基调：产品基调 1 段（受众/气质/约束）+ 明确排除项（禁什么字体/配色套路）
    ↓
2. 三层 token：primitive → semantic → component
    裸值只许出现在 primitive；semantic/component 只能引用上一层
    ↓
3. 组件×状态：manifest.components[] 逐组件补四态 + 跨模块五状态
    ↓
4. 展示页：components.html / states.html（渲染器生成，评审一眼看全套）
    ↓
5. 门禁自检：check_design.py 过 G1–G8，design 字段写回 manifest
```

### 基调

一段话说清「这套界面看上去应该像什么」：目标用户、行业气质、品牌约束、想给客户的感受。
不写功能清单。同时写**明确排除项**——禁用什么字体、什么配色套路（G6）。
基调是后面所有 token 决策的裁判：两个方案拿不准时，回基调裁决。

### 三层 token

`primitive`（原始色值/字号/间距/圆角）→ `semantic`（语义变量）→ `component`（组件变量）。
硬规则：**semantic 与 component 层禁止裸值**（hex / 随意 px），只能引用上一层；
违反即被 G2 扫描打回。产出写进 `DESIGN.md` 并派生 `tokens.css`，两层同源不双写。

### 组件×状态

组件来自 `manifest.components[]`（jf-ia 已定，本步骤**补状态不增删组件**）。
每个组件四态齐全：`default` / `hover` / `active` / `disabled`；
跨模块五状态全部定义：`empty` / `loading` / `error` / `disabled` / `permission-denied`
——这批状态评审时最常被问、也最常被漏，漏一个就是一次返工。

### 展示页

`jf-uxprompt` 渲染器从 `components-and-states.md` 生成两个展示页：
`prototypes/components.html`（逐组件逐状态）、`prototypes/states.html`（跨模块五状态）。
每页 meta 行标注「设计基线：DESIGN.md」并链到两个展示页。

### 门禁自检

```bash
# 校验设计基线（G1–G8）
python3 products/jiaofu/jf-design/scripts/check_design.py manifest.json

# 机读报告 / 脚本自检
python3 products/jiaofu/jf-design/scripts/check_design.py manifest.json --json
python3 products/jiaofu/jf-design/scripts/check_design.py --self-test
```

退出码：`0` 通过｜`1` 未通过｜`2` 用法错误。**不通过 = 本步骤未完成**，
禁止进入 jf-wireframe。

## 门禁 G1–G8

| 码 | 条件 | 级别 |
|---|---|---|
| G1 | `DESIGN.md` 存在且含全部必含段落（基调/色板/字体/间距栅格/语义变量/组件变量/排除项） | ERROR |
| G2 | 三层结构完整；semantic/component 层无裸值（扫 `#[0-9a-fA-F]{3,8}`） | ERROR |
| G3 | 组件按「类型」列分档：**交互**组件四态齐全（default/hover/active/disabled）；**容器**组件四态可标 `—`，但表下必须有 `- \`<id>\`：` 落点说明 | ERROR |
| G4 | 跨模块五状态全部定义（empty/loading/error/disabled/permission-denied） | ERROR |
| G5 | 组件能追溯到 `manifest.components[]` 的 id | ERROR |
| G6 | 排除项明确（至少写明禁用的字体/配色套路） | ERROR |
| G7 | `tokens.css` 与 `DESIGN.md` 落地一致：无漂移 / 无未声明变量 / 引用不偏 / 不越级 / 不断链成环 | ERROR |
| G8 | 「组件×状态」表 `引用 token` 列可解析：具名 token 必须存在（ERROR）；`族-*` 通配空命中给 WARN | ERROR / WARN |

G3 的「类型」列留空按 `交互` 处理（向后兼容早期只写四态的文件）。
容器组件不写「类型」却把四态标成 `—`，会照旧报 G3——分档是为了让容器
**有路可走**，不是给交互组件开后门。

模板与硬规则全文：`references/design-contract.md`（含反模式清单，评审门禁用）。

## 保留 vs 外包（jf-* 只做编排/契约/门禁）

| 环节 | jf-design 保留 | 外包执行 | 降级 |
|---|---|---|---|
| 三层 token 结构 | 结构定义 + 门禁（G2 禁裸值） | `ui-ux-pro-max:design-system`（generate-tokens.cjs / validate-tokens.cjs） | 内置简洁单色规范（渲染器内置 tokens.css 作 primitive 初稿） |
| 设计方向规划 | 门禁：基调 1 段 + 排除项（G1/G6） | `impeccable init`（PRODUCT.md）/ `impeccable shape`（写代码前先规划 UX/UI） | 直接用内置规范 |
| 组件×状态表 | 表格契约 + 四态门禁（G3/G4/G5） | `ui-ux-pro-max:design-system` states-and-variants | 按 `manifest.components[]` 自动生成骨架表 |
| 视觉评审 | 反模式清单（design-contract.md） | `impeccable critique` / `audit` | 人工按清单核对 |

**没配外部 skill → 本 skill 自行执行，不阻塞链路；配了就以它为准，调用失败即硬失败**：按
`references/design-contract.md` 的模板手工产出 `DESIGN.md` + `components-and-states.md`
（primitive 用内置简洁单色规范的值起步），过 G1–G8 即算完成。

**外包不改变契约**：外部 skill 产出设计基线时，必须交出同结构文件并通过门禁；
只交零散样式视为未完成。

## 与渲染器的对接

`jf-uxprompt` 渲染器优先消费外部基线（读 `manifest.design`）：

- `design.tokens` 指向的文件存在 → **直接复用，不覆盖、不重新生成**内置 tokens.css
- `design.spec` / `design.states` 文件存在 → 每页 meta 行标注「设计基线」并链接展示页
- `design` 缺失或文件不存在 → 内置简洁单色规范降级（渲染 `--strict` 下给 WARN「未接入设计基线」）

## 纪律

- **先基线后页面**：第一页线框开画前 G1–G8 必须全过
- **裸值只在 primitive**：semantic/component 出现裸 hex 即打回（G2）
- **DESIGN.md 是真相源**：tokens.css 由它派生，双写冲突时以 DESIGN.md 为准（G7 核对）；
  内置 tokens.css 仅在无 DESIGN.md 时生成
- **容器不装交互**：页面外壳、表格这类容器四态落在子部件上，标 `—` 就必须写落点说明
  （G3）——渲染器按「类型」列分派示意件，不会给容器画一颗并不存在的「主操作」按钮
- **不做视觉决策**：选什么颜色/字体是执行者的事，本 skill 只定结构与门禁
- **禁猜组件**：组件来自 `manifest.components[]`，本 skill 补状态不增删组件
- **缺状态即打回**：不让「忘了画 disabled」留到客户评审（G3/G4）

## 项目适配

本 skill 通用，不绑特定项目。以下可按项目调整：

- **目录路径**：`DESIGN.md` / `components-and-states.md` / `tokens.css` 的位置由项目结构决定，写进 `manifest.design` 即可
- **执行外包**：本步骤（中央表 **S2**，设计基线 5 块）的执行可由外部 skill 完成。jf-* 只管编排和门禁——只要产出过门禁，谁做的无所谓。未外包时本 skill 自行执行。候选与安装命令见中央登记表 `jf-contract/references/external-skills.md`（含 `ui-ux-pro-max` 顶层与 `design-system` 子 skill 的分工理顺：素材归顶层，token 落盘归子 skill）
- **推荐默认**：色板规模、字阶档数等视觉决策由执行者定，本 skill 不预设
