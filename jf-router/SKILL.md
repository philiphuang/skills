---
name: jf-router
description: 交付套件入口路由器。先解析用户意图落在高保真工作法四层工作流的哪个环节，再强制路由到正确的 jf-* skill，从源头开始执行。
---

# jf-router

**所有 jf-* skill 的前置入口。** 用户调用任何 jf-* skill 时，先通过 jf-router 判断意图应落在高保真工作法四层工作流的哪个环节，再强制路由到正确的 skill。目标是让工作流始终"从源头开始"，避免在下游 skill 里发现上游还没理清楚。

## 核心职责

1. **意图分类**：把用户消息映射到 jf-* 套件中的某个 skill
2. **强制路由**：当调用 skill ≠ 目标 skill 时，终止当前调用，按目标 skill 执行
3. **可解释**：给出路由理由和命中信号词，让用户理解为什么被切过去

本 skill 只做分类，不做内容生成、不追踪块就绪状态、不执行具体工作法的步骤。

## 输入/输出契约

### 输入

```text
user_message: string      // 用户原始消息
called_skill: string      // 用户调用的 skill 名，如 jf-wireframe
context?: string          // 可选：当前会话上下文摘要
```

### 输出

```text
target_skill: string      // 路由目标 skill 名
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
按优先级链仲裁 → 得到 target_skill
  ↓
判断 verdict = (target_skill == called_skill)
  ↓
输出路由结果
  ↓
若 mismatch → 当前会话切到 target_skill 执行
若 match → 继续原 skill 流程
```

## 分类规则

### 1. 四层工作流到 skill 的映射

| 工作流层 | 内容块 | 目标 skill |
|---------|--------|-----------|
| 1.0 业务层 | PV/BRO/BEN/CP/UC/JF/BR/SM/FL | jf-mrd |
| 2.0 设计层 — PRD | FR/AC/API/RP/PP | jf-prd |
| 2.0 设计层 — IA | PS/LT/NM/FA | jf-ia |
| 2.0 设计层 — 数据 | DC/CDF/TFD | jf-data |
| 2.0 设计层 — 线框 | EC/PW/TS/SV/MS/DDR/GC/CSM | jf-wireframe |
| 2.0 设计层 — 生成 | PC/PB/LF/DD/CS | jf-uxprompt |
| 3.0 验证层 | BDD/TC | jf-test |
| 横切 — 评审 | PRS/12项客户清单 | jf-review |

> **工作流无「规格层」**：「规格」不是产出物——MRD 决策记录（DR）承担决策，PRD 承担需求规格化。用户提及「规格」时路由到 jf-mrd（决策未拍板）或 jf-prd（已拍板），不产生中间文档。

### 2. 路由优先级链

```
1.0 jf-mrd
  ↓
2.0 jf-prd
  ↓
2.0 jf-ia  ≈  jf-data
  ↓
2.0 jf-wireframe
  ↓
2.0 jf-uxprompt
  ↓
3.0 jf-test
  ↓
4.0 （非 jf-*，通用开发）
```

- **同层多个 skill 命中**：取该层最上游的 skill（按优先级链）
- **jf-ia 与 jf-data 同时命中**：两者并行，但 jf-prd 是共同前置。若是从源头角度，优先 jf-prd
- **jf-review 调用但无已产出物**：拒绝，提示从 jf-mrd 开始

### 3. 模糊词归类

| 用户说的 | 默认归类 | 例外 |
|---------|---------|------|
| 需求 | jf-mrd | 明确说"功能需求/AC"→jf-prd |
| 设计 | jf-ia | 明确说"线框"→jf-wireframe；"生成"→jf-uxprompt |
| 页面 | jf-ia | 明确说"画线框"→jf-wireframe；"生成页面"→jf-uxprompt |
| 数据 | jf-mrd | 明确说"建表/数据库/字段"→jf-data |
| 状态 | jf-mrd | 明确说"状态变体"→jf-wireframe |
| 权限 | jf-prd | 明确说"页面权限"→jf-ia |
| 生成/写代码 | jf-uxprompt（若2.0未开始） | 2.0全部完成且门禁通过→4.0 |
| 测试 | jf-test | 无AC时→jf-prd |
| 评审/汇报 | jf-review（有产出时） | 无产出→jf-mrd |
| 组件 | jf-wireframe | 编码实现→4.0 |

## 强制路由行为

### 当 verdict = match

输出确认：

```text
已确认你的意图与 [called_skill] 匹配。
命中信号词：[matched_signals]
理由：[reason]
```

继续执行 called_skill 的正常流程。

### 当 verdict = mismatch

输出路由决定：

```text
⚠️ 路由切换

你的意图命中信号词：[matched_signals]
属于工作流 [层] — [目标skill]。
当前调用 [called_skill] 不是正确入口。

正在切到 [target_skill]，从源头开始执行。

理由：[reason]
```

然后终止当前 skill，按 target_skill 的 SKILL.md 在当前会话中继续工作。

## 边界情况

| 场景 | 处理 |
|------|------|
| 用户意图跨层（如"从 MRD 做到线框"） | 拒绝：提示分步进行，先定位到最上游 skill |
| 用户意图不在任何 jf-* 范围 | 透传：不强制路由，让 called_skill 自行处理 |
| jf-review 调用但无产出物 | 拒绝："jf-review 是组装汇报材料，当前无产出物可组装。请先从源头 skill 开始。" |
| 用户明确覆盖路由 | 尊重用户：用户说"跳过路由，直接进入 [skill]"→按用户意图执行 |
| 信号词完全未命中 | 默认透传 called_skill，不做路由 |

## 引用资料

- 信号词表：`references/signal-words.md`
- 工作法来源：`src/工作法/高保真/高保真工作法.md`（skills-factory 仓库内；仓库外不可用，路由分类不受影响）

## 项目适配

- 路由规则是指导性的，依赖 agent 语义理解，不是硬编码正则
- 新加入 jf-* 套件时，只需更新本文件的"映射表"和"优先级链"
- 非 jf-* skill 不经过本路由
