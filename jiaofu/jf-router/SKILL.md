---
name: jf-router
description: 交付套件入口路由器。先解析用户意图落在高保真工作法三拍的哪一拍，再强制路由到正确的门面或模块，从源头开始执行。判跨拍，不判拍内。
---

# jf-router

**所有 jf-* skill 的前置入口。** 用户调用任何 jf-* skill 时，先通过 jf-router 判断意图应落在
三拍的哪一拍，再强制路由到该拍的**门面**（或用户显式指名的模块）。目标是让工作流始终
"从源头开始"，避免在下游 skill 里发现上游还没理清楚。

## 核心职责

1. **判跨拍**：把用户消息映射到**某一拍**——`jf-mrd`（①业务事实）/ `jf-prd`（②需求与设计）
   / `jf-review`（③客户评审）
2. **定落点**：该拍的门面，或用户显式指名且确实属于该拍的模块
3. **强制路由**：当调用 skill ≠ 落点时，终止当前调用，按落点执行
4. **可解释**：给出路由理由和命中信号词，让用户理解为什么被切过去

**判拍内不是本 skill 的事**——进了某一拍，由那一拍的门面按它的步骤表找「第一个产物不存在
∨ 门禁没过」的步骤。本 skill 只做分类，不生成内容、不追踪块就绪状态。

## 输入/输出契约

### 输入

```text
user_message: string      // 用户原始消息
called_skill: string      // 用户调用的 skill 名，如 jf-wireframe
context?: string          // 可选：当前会话上下文摘要
```

### 输出

```text
target_skill: string      // 路由落点 skill 名（门面，或显式指名的模块）
target_stage: string      // 落在哪一拍：①业务事实 | ②需求与设计 | ③客户评审 | 基建
verdict: match | mismatch // 调用与意图是否一致
matched_signals: string[] // 命中的信号词（解释性）
reason: string            // 一句话路由理由（中文）
```

## 路由决策流程

```
用户调用 jf-*
  ↓
读取 jf-router 分类规则
  ↓
对照 signal-words.md 标注用户消息命中的信号词
  ↓
第一步：定拍（①/②/③/基建）
  ↓
第二步：定落点（显式指名且属该拍 → 那个模块；否则 → 该拍门面）
  ↓
判断 verdict = (target_skill == called_skill)
  ↓
输出路由结果
  ↓
若 mismatch → 当前会话切到 target_skill 执行
若 match → 继续原 skill 流程
```

## 分类规则

### 1. 三拍到 skill 的映射

| 拍 | 内容块 | 门面 | 拍内模块 |
|----|--------|------|---------|
| ① 业务事实 | PV/BRO/BEN/CP/UC/JF/BR/SM/DR | `jf-mrd` | `jf-mrd-core`（业务建模本体）、`jf-review-core`（业务评审材料组装） |
| ② 需求与设计 · 设计生产段 | shaping 8 件套 | `jf-prd` | `jf-interview` |
| ② · 设计生产段 | FR/AC/API/RP/PP（含 FL 功能清单规划） | 同上 | `jf-prd-core` |
| ② · 设计生产段 | BO/PS/LT/NM/FA | 同上 | `jf-ia` |
| ② · 设计生产段 | DC/CDF/TFD | 同上 | `jf-data`（独立链，绕开 PRD） |
| ② · 设计生产段 | DESIGN/components-states | 同上 | `jf-design` |
| ② · 设计生产段 | EC/PW/SV/MS/DDR/GC/CSM | 同上 | `jf-wireframe` |
| ② · 设计生产段 | manifest → 多页原型；元提示词块 PC/PB/LF/DD/CS | 同上 | `jf-uxprompt` |
| ② 需求与设计 · 交付研发段 | BDD/TC | `jf-prd` | `jf-test`（**归属②，时序在出口 B 之后**） |
| ③ 客户评审 | 13 项客户清单（业务 6 + 设计 7）；产物B 设计注释 | `jf-review` | `jf-review-core`（与 ① 共用） |
| 基建 — 契约 | manifest 字段/I1–I12/跳转协议/标注协议 | — | `jf-contract` |
| 基建 — 验证 | manifest/prototype 校验 | — | `jf-validate` |

> **工作流无「规格层」**：「规格」不是产出物——MRD 决策记录（DR）承担决策，PRD 承担需求规格化。
> 用户提及「规格」时路由到 ①（决策未拍板）或 ②（已拍板），不产生中间文档。

> **基建不属于任何一拍**：`jf-contract` 与 `jf-validate` 跨拍被引用，不参与定拍竞争。

### 2. 定拍优先级链

**顺序不能跳**——「从源头开始」就是这个顺序的字面意思：

```
① jf-mrd                     ← 业务事实
   ↓ 出口 A · MRD front-matter status: 已确认
② jf-prd（设计生产段）        ← jf-interview → jf-prd-core → jf-ia ≈ jf-data
                                → jf-design → jf-wireframe → jf-uxprompt
   ↓ 设计生产段出口（= ③ 的入口条件）
③ jf-review                  ← 材料组装 → 设计评审 → 产物B → 答复分流
   ↓ 出口 B · 开发授权
② jf-prd（交付研发段）        ← jf-test
   ↓
非 jf-*（通用开发）
```

- **同一拍内多个 skill 命中**：交给该拍**门面**去判拍内次序（见下节「拍内次序」）
- **访谈意图词优先于对象词**：消息含「讨论/聊聊/想想/拿不准/待确认/拍板/口径冲突」时，
  无论对象是需求还是设计，落 `jf-interview`（它在 ②1）——讨论本身就是要收敛待确认；
  已定型（shaping 8 件套过门禁且无待确认）则按对象词正常归类
- **jf-review 调用但无已产出物**：拒绝，提示从 `jf-mrd` 开始
- **jf-contract 与 jf-validate 的分工**（两者都围绕 manifest，最易混）：问契约**怎么写**——
  字段含义、I 编号、跳转/标注协议怎么落 → `jf-contract`；要产物**对不对**的结论——
  跑校验、看报错 → `jf-validate`。一个是定义，一个是门禁，别互相顶替

### 3. 拍内次序（门面自己用，router 只判断「是不是同一拍」）

```
②: jf-interview > jf-prd-core > jf-ia ≈ jf-data > jf-design
    > jf-wireframe > jf-uxprompt > jf-test
①: jf-mrd-core（① 内没有别的生产模块）
```

`jf-ia` 与 `jf-data` 并行，同时命中时优先 `jf-prd-core`（它是共同上游）；
`jf-design` 在 IA 之后、线框之前，是两者的公共设计基线。

### 4. 模糊词归类

**先看拍级触发词**——命中了就直接落到那一拍的**门面**：

| 用户说的 | 拍 | 门面 |
|---------|-----|------|
| 理清业务 / MRD / 需求整理 / 业务规则 | ① 业务事实 | `jf-mrd` |
| 写 PRD / 功能需求 / 验收标准 | ② 需求与设计 | `jf-prd` |
| 阶段汇报 / 客户评审 / 需求确认 / 设计评审 | ③ 客户评审 | `jf-review` |

**拍级触发词以三个门面的 `description` 为准**——上表是它的分类视图，改一处必须改两处。
没命中拍级词的，按下面这张专业词表落到**模块**：

| 用户说的 | 默认归类 | 例外 |
|---------|---------|------|
| 需求 | `jf-mrd-core` | 明确说"功能需求/AC"→`jf-prd-core`；"讨论需求/需求拿不准"→`jf-interview` |
| 讨论/聊聊/想想/拿不准 | `jf-interview` | 已定型→`jf-prd-core` |
| 待确认/拍板/口径冲突 | `jf-interview` | — |
| 设计 | `jf-ia` | 明确说"线框"→`jf-wireframe`；"生成"→`jf-uxprompt` |
| 设计体系/风格/组件规范 | `jf-design` | 线框内的单组件→`jf-wireframe` |
| 页面 | `jf-ia` | 明确说"画线框"→`jf-wireframe`；"生成页面"→`jf-uxprompt` |
| 数据 | `jf-mrd-core` | 明确说"建表/数据库/字段"→`jf-data` |
| 状态 | `jf-mrd-core` | 明确说"状态变体"→`jf-wireframe` |
| 权限 | `jf-prd-core` | 明确说"页面权限"→`jf-ia` |
| 生成/写代码 | `jf-uxprompt`（若②设计生产段未完成） | 全部完成且门禁通过→非 jf-* |
| 测试 | `jf-test` | 无 AC 时→`jf-prd-core` |
| 契约/字段含义/manifest 怎么写 | `jf-contract` | 要"生成页面"→`jf-uxprompt`；要"校验对不对"→`jf-validate` |
| 校验/检查/对不对 | `jf-validate` | 测试→`jf-test`；问"字段什么意思"→`jf-contract` |
| 评审/汇报 | `jf-review`（有产出时） | 无产出→拒绝，指向 `jf-mrd` |
| 组件 | `jf-wireframe` | 编码实现→非 jf-* |

### 5. 拍级路由（不是模糊词时）

命中拍级触发词或用户意图明确指向某一拍，但**没有显式指名任何 skill** → 落**该拍的门面**：

| 落在 | 门面 |
|------|------|
| ① 业务事实 | `jf-mrd` |
| ② 需求与设计 | `jf-prd` |
| ③ 客户评审 | `jf-review` |

用户**显式指名**了某个 skill：

| 情况 | 落点 |
|------|------|
| 指名的 skill **属于**这一拍 | 就是它自己（match）——**模块可独立调用**，行为与门面编排无关 |
| 指名的 skill **不属于**这一拍 | 切到这一拍的**门面**（mismatch）——门面再判拍内从第几步进 |

## 强制路由行为

### 当 verdict = match

输出确认：

```text
已确认你的意图与 [called_skill] 匹配。
命中信号词：[matched_signals]
理由：[reason]
```

继续执行 called_skill 的正常流程。**模块命中时不再往上顶**——显式指名 `jf-mrd-core`
就是 `jf-mrd-core`，不切成 `jf-mrd`。

### 当 verdict = mismatch

输出路由决定：

```text
⚠️ 路由切换

你的意图命中信号词：[matched_signals]
落在 [拍]（如：① 业务事实）。
当前调用 [called_skill] 不是这一拍的落点。

正在切到 [target_skill]（[门面|模块]），从源头开始执行。

理由：[reason]
```

然后终止当前 skill，按 target_skill 的 SKILL.md 在当前会话中继续工作。

## 边界情况

| 场景 | 处理 |
|------|------|
| 用户意图跨拍（如"从 MRD 做到线框"） | 拒绝：提示分步进行，先定位到最上游的拍 |
| 用户显式指名模块（如"用 jf-mrd-core 整理业务规则"） | 判跨拍——属该拍则 match 直接执行；不属则切该拍门面 |
| 用户意图不在任何 jf-* 范围 | 透传：不强制路由，让 called_skill 自行处理 |
| MRD 存在 `[待确认]` 且已进入 ② | 打回 `jf-interview`：先收敛待确认，再进 PRD |
| jf-review 调用但无产出物 | 拒绝："jf-review 是组装汇报材料，当前无产出物可组装。请先从 jf-mrd 开始。" |
| 用户明确覆盖路由 | 尊重用户：用户说"跳过路由，直接进入 [skill]"→按用户意图执行 |
| 信号词完全未命中 | 默认透传 called_skill，不做路由 |

## 引用资料

- 信号词表：`references/signal-words.md`
- 工作法来源：`src/工作法/高保真/高保真工作法.md`（工厂内注记，部署后不可用；路由分类不受影响。**母文档仍是四层叙事**——本 skill 用三拍分类，不读它的层号）

## 项目适配

- 路由规则是指导性的，依赖 agent 语义理解，不是硬编码正则
- 新加入 jf-* 套件时，只需更新本文件的"映射表"和"定拍优先级链"
- 非 jf-* skill 不经过本路由
