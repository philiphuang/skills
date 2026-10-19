# 定时运行与状态管理（#110 锁定，2026-10-03）

> ⚠️ **遗留（v1）**：本规范服务于 v1 管线（run/finalize）。主路径已由 v2 getter（`list-new`/`fetch`，见 `getter-spec.md`，#202/#205/#206）取代——v2 零调度（编排属调用方），agent 中立；本文件仅在运行 v1 遗留命令时有效。
> 定时编排已另定（2026-10-17）：multica autopilot，见 `references/automation-multica.md`
> （取代本文 §1「ZCode 客户端并列新建」及 #110 对应决策）。

本文件是 qianwen-minutes-sync 管线调度与状态管理的规范唯一事实源，#111 实现按此消费。
决策过程见 issue #110（用户授权直接裁定）。
先例：imness 飞书采集自动化（prompt 存档 `.scratch/qianwen-minutes-sync/references/imness-automation-prompt.md`
——工作日判断/编排与核心分离/结构化运行报告三点借鉴已在文件末列明）、imness `index.json` 会话游标范式。

## 1. 并合形态：并列新建

- 独立新建一条 ZCode 客户端自动化，**不并入** imness 采集 prompt——故障域隔离（任一挂掉不影响另一条）、独立开关、可错峰
- 运行现场：2606国际公司MCloud 项目 workspace（与 imness 采集同现场，2026-08-22 用户已定）
- prompt 存档：`.scratch/qianwen-minutes-sync/references/qianwen-sync-automation-prompt.md`（#111 落地）
- 编排（prompt）与核心（脚本）分离；脚本可独立手跑

## 2. 频率与工作日

- 每两小时，与 imness 采集**错峰约 30 分钟**（具体注册分钟 #111 定，原则=不与 imness 同时起跑）
- 工作日判断直接复用 imness 方案：WebFetch `http://timor.tech/api/holiday/info/$TODAY` →
  `type.type`：0=工作日执行、4=调休补班执行、1/2/3=休息日输出「跳过」并结束；API 失败 fallback cron 周一至周五

## 3. watermark 双层

- **拉取层 = 会话游标 state.json**（抄 imness index.json）：
  `.scratch/qianwen-minutes-sync/state.json`，`conversations[]` 每条 `{id, title, updated_at, done}`；
  增量条件 = `entry=audio_qianwen` 且（不在 state 或 `updated_at` 变化）
- **归档层 = 文件名即状态**（#108 已锁）：目标路径同名文件存在即跳过
- 冲突语义：`done` 后 `updated_at` 再变（用户在会话里追加对话，纪要本体通常不变）→
  只更新 state 不重新归档；确需重归档时人工删文件
- state 永不自动清；中转文件分类完成即清（#108）

## 4. 认证自检与告警

- 每 run 第一步探活：`GET /api/v1/conversations` 第一页
- 非 200 / 空列表 / 登录失效特征 → 报告「**Cookie 失效，需人工续**」并终止本次 run
  （不重试轰炸、不写 state）；续期流程按 #107 锁定：Cookie 快照 + 人工续，不存凭据
- qianwen 侧具体失效特征未实测 → #111 首批验证点（#107 已列：Cookie 字段/有效期/失效特征、分页上限）

## 5. 日志与留痕

- `sync.log`（抄 imness sync.log 行范式，追加写）：`时间 | 阶段 | 会话标题 | 动作(归档/待分拣/跳过) | 结果`
- `router-log.jsonl`：分类决策审计（#109，含 LLM reason）
- 运行报告 = 会话尾部结构化总结（天然告警通道）+ `tail sync.log`
- 三者都在 `.scratch/qianwen-minutes-sync/` 下，与 state/中转同区
