# 分类判定引擎与待分拣流程（#109 锁定，2026-10-03）

> ⚠️ **遗留（v1）**：本规范服务于 v1 管线（run/finalize）。主路径已由 v2 getter（`list-new`/`fetch`，见 `getter-spec.md`，#202/#205/#206）取代——v2 不做分类，落库分类由 docness 承担；本文件仅在运行 v1 遗留命令时有效。

本文件是 qianwen-minutes-sync 管线分类引擎的规范唯一事实源，#111 实现按此消费；
front-matter 字段见 `archive-spec.md`（#108）。决策过程见 issue #109（用户授权直接裁定）。
先例：imness router 两段式（确定性过滤 + agent 调 LLM，脚本不内嵌 API 调用）、
待审池「文件即状态」；docness `UNCERTAIN` 哨兵。

## 1. 判定引擎：混合两段式

**第一段——确定性关键词（脚本内，零成本，可独立手跑）**

- 输入：纪要标题 × projects-map 条目（文件顺序即优先级，#108 已锁）
- 唯一命中 → `confidence: high`，`matched_keyword: <命中词>`，归档
- 多条目命中 → 按映射序取首，`confidence: medium`
- 无命中 → 进第二段

**第二段——LLM 判定（automation 现场 agent 调，脚本只产 prompt 不调模型）**

- 脚本产出 `ai_prompt`：纪要标题 + 摘要（messages 的 `assistant/summary`）+ projects 全条目（name/keywords/description）
- agent 返回 JSON `{"project": <id|null>, "reason": "..."}`；project 非空且在映射中 → `confidence: medium`，`matched_keyword: llm`
- 返回 null / 不在映射 / 解析失败 → 待分拣（docness UNCERTAIN 哨兵同义）
- **手跑无 agent 时第二段整体跳过**：无命中直接待分拣——可独立手跑、不依赖 API key

**边界（#108 已锁定的重申）：映射是唯一分类事实源，LLM 只能从映射既有条目里选，不能创造新归档目标。**

## 2. 置信度语义

| confidence | 含义 |
|---|---|
| high | 关键词唯一命中 |
| medium | 多命中按映射序取首 / LLM 判定命中 |
| low | 待分拣（无命中且无 LLM 结果 / LLM UNCERTAIN） |

## 3. 待分拣流程（文件即状态，抄 imness 待审池语义）

- 落待分拣收件箱（`defaults.inbox_dir`），front-matter：`classification.project: null`、`confidence: low`、`status: pending`
- **每次 run 先重扫待分拣目录**：`status: pending` 且经第一段已能确定性命中 → 自动归档（#108 维护流程「补映射后重跑管线归档」的落地）
- 人工处理二选一：
  1. 直接把文件 mv 到正确归档目录并补 front-matter；
  2. 只修 projects-map，等下次 run 自动归档
- 每条分类决策（归档/待分拣/跳过）追加 `router-log.jsonl` 审计（含 LLM reason）

## 4. 提醒方式

- **不引入独立通知通道**（macOS 通知/飞书消息不做，与 imness 同立场：通知类 Out of Scope）
- 提醒 = 每次 run 会话尾部结构化运行报告（ZCode 会话输出天然呈现）
- 报告必含：新增纪要 N（归档 N₁ / 待分拣 N₂）、待分拣标题清单、Cookie 探活状态
- 待分拣积压 > 5 → 报告加显式警告行

## 5. 新工作发现

- 待分拣清单即新工作信号，不做额外发现机制
- 报告附建议行：「重跑 gen_projects_map --dir /opt/prjs 或手工加条目」
- 不自动改映射（映射人工维护，#108 锁定）
