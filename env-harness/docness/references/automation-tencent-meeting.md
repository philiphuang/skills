# 腾讯会议逐字稿定时采集（multica autopilot）

> 2026-10-18 逐字稿版：取代 2026-10-17 上线的智能纪要采集（同 autopilot `21b9eca7` 原地改造）。
> 采集物为**逐字稿**（官方转写全文，非智能纪要摘要）；项目归属判定、待分类池、三件套入库与千问同构（见 `project-routing.md`）。
> 实现载体：`tencent-meeting-transcript-sync` getter（脚本直调 MCP，agent 中立）；编排由本 autopilot prompt 承担。

## 注册参数

| 项 | 值 |
|----|----|
| 载体 | multica autopilot `21b9eca7-69ff-4f44-90ee-1f1e7244918c` |
| 标题 | 工作日拉取腾讯会议逐字稿 |
| 节奏 | 工作日每日 2 轮：11:30 / 16:30（错开千问 10:30/17:30 与飞书采集整点体系） |
| 执行机 | oyun（Oracle A1）；agent `f754fd3e`（腾讯会议采集） |
| 前置 | `TENCENT_MEETING_TOKEN` 在 `~/.secrets/tencent-meeting.env`；getter 在 `/p/skills-factory/products/tencent-meeting-transcript-sync/scripts/` |
| 水位 | `/p/2606国际公司MCloud/.scratch/tencent-meeting-transcript-sync/state.json`（`last_run` + `meeting_ids[]` + `processed_record_file_ids[]`，各 500 条上限） |
| sched-audit 标签 | `multica:腾讯逐字稿(工作日 11:30/16:30)`（阈值 30h） |

## Prompt 原文（注册时粘贴此节）

> 见 autopilot 当前 description；规范唯一事实源在
> `products/tencent-meeting-transcript-sync/references/getter-spec.md`。

## 与智能纪要的关系

- 逐字稿 getter 上线当天（2026-10-18），智能纪要采集 prompt 退役删除（#216 锁定）
- 已入库的历史纪要文件不动
- 水位文件独立（`tencent-meeting-transcript-sync/state.json` vs 旧 `tencent-meeting-sync/state.json`），不复用纪要水位

## 失败语义

- Token 失效（鉴权失败 / 退出码 2）→ 原样报告并结束，不重试不改文件，等人工到 ai-skill 页重取 Token
- 单场会议取件失败不影响其余：记录原因继续下一场
- 转写中（`state_int != 3`）：本轮跳过，下轮增量自然重试
