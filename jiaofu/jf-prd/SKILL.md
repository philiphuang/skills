---
name: jf-prd
description: 交付②·需求与设计——把已确认的业务事实做成可验收的需求规格与可点通的页面。触发：写PRD、功能需求、验收标准。
---

# 拍② 需求与设计

## 这一拍是什么

把①已确认的**业务事实**，做成两样东西：

- **可验收的需求规格**——FR / AC / API / RP / PP，研发照着能做
- **可点通的页面**——`manifest.json` 串起的多页原型，客户照着能看

本拍的出口产物交客户做**设计评审**——确认「逻辑层之上，界面与架构对不对」。

## 入口

**上游条件**：MRD 产物的 front-matter 里 `status: 已确认`（= ①出口 A 已过，客户业务评审通过）。
读不到这个字段，或值不是「已确认」，**本拍不该启动**。

**拍内判定**：按上表顺序找第一个「产物不存在 ∨ 门禁没过」的步骤，从那一步继续。
不重跑已经绿的步骤。

## 拍内步骤表

### 设计生产段

| 步骤 | 执行者 | 输入 | 输出 | 门禁 | 回退 |
|---|---|---|---|---|---|
| 1 收敛 `[待确认]` | `jf-interview` | MRD | `shaping/` 8 件套 + 待确认清单 | `check_shaping.py` G1–G7 | 硬失败 |
| 2 需求规格 | `jf-prd-core` | MRD + shaping | FR / AC / API / RP / PP | 无（不外包） | — |
| 3 信息架构 | `jf-ia` 〔+ `impeccable`〕 | 需求规格 + MRD | **`manifest.json`** + PS / LT / NM / FA | `validate_manifest.py --strict` | 硬失败 |
| 4 数据模型 | `jf-data` | ①CP + BEN（**独立链**，绕开②） | DC / CDF / TFD | 无（不外包） | — |
| 5 设计基线 | `jf-design` 〔+ `ui-ux-pro-max`〕 | `manifest.json` | `DESIGN.md` / `components-and-states.md` / `tokens.css` | `check_design.py` G1–G8 | 硬失败 |
| 6 线框 | `jf-wireframe` 〔+ `impeccable`〕 | `manifest.json` + 设计基线 | EC / PW / SV / MS / DDR / GC / CSM | `validate_manifest.py`（manifest 侧） | 硬失败 |
| 7 渲染 | `jf-uxprompt` 〔+ `frontend-design`〕 | `manifest.json` + 设计基线 | `prototypes/`（评审树；`--demo` 另出演示树） | `validate_manifest.py --strict` + `jf_contract_check.py` + `check_demo_separation.py` | 硬失败 |

### 交付研发段（在客户反馈回流之后）

| 步骤 | 执行者 | 输入 | 输出 | 门禁 | 回退 |
|---|---|---|---|---|---|
| 8 BDD 场景 / 测试用例 | `jf-test` | AC + 客户反馈 | BDD 场景 / 测试用例 | 无（不外包） | — |

第 8 步为什么排在后面：**归属与执行分开**。`jf-test` 归本拍（它是交付研发的一部分），
但它消费客户反馈，而反馈要等③的设计评审回流——这是**时序**，不是归属。

**〔〕里是可选的外部执行者**。配置了就**不降级**：该外部 skill 成为这一步的**前置要求**，
调用失败即硬失败。没配置就走内置路径，链路照跑。

**推进判据**：产物存在 ∧ 有门禁的必须过（退出码 0）。本拍**不新增判据**。

## 出口判据

1. 上表设计生产段的产物清单齐全
2. 全部门禁退出码 0
3. 交付研发段（含 `jf-test`）的产物在客户反馈回流之后补齐

设计生产段出口即③的入口条件。

## 调用契约

**正常路径**：`jf-router` 判为跨拍落点在本拍 → 本文件按上表顺序调 8 个模块，
逐步收退出码；某一步红了就停下问人，不跳步。

**独立路径**：用户显式指名任一模块（`jf-ia` / `jf-data` / `jf-design` / …）时可直接调用——
此时它先走 `jf-router` 判跨拍，再进自己的流程。模块行为与本拍编排无关，可独立测试。

## 公共设施

跨拍路由 `jf-router`、契约 `jf-contract`、门禁 `jf-validate`——用途统一见 `index.md` 的
「公共设施」一节。本拍**额外点名其中两个**：

- **`jf-contract`**——`manifest.json` 的字段怎么写、I1–I12 说什么，权威在它那里；
  本拍的第 3–7 步全在读写这份 manifest
- **`jf-validate`**——产物对不对的机器结论；上面七道门禁有一半是它的脚本
