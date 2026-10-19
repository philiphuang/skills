# 定时采集家族（multica）总览

> 2026-10-17 统一盘定：内容采集类定时任务统一落在 **multica autopilot**，一个体系管理、
> 错峰起跑、独立开关。分拣维度始终是 **docness 分类目录**（会议纪要/技术资料/…）与
> **项目工作区**（projects-map），不按来源工具（千问/腾讯会议/微信）建目录；
> 判不定归属的内容统一进**待分类池**等人认领（`project-routing.md`）。

## 任务清单

| 任务 | multica id | 节奏 | 采集物 | 入库链路 | 状态 |
|------|-----------|------|--------|---------|------|
| 飞书采集 | `e94fa6e4` | 工作日 8-18 多轮 | 飞书会话消息 + 妙记链接 | imness 采集/ingest；妙记→docness 4c | 运行中 |
| 笔记同步（微信文档收藏） | notehelper-sync（id 见 multica） | */2h | 微信收藏文章 | 落 `p/kb/收件箱/笔记同步助手/`，kb ingest 管线消化 | 运行中 |
| 千问拉取 | `ca967103` | 工作日 10:30 / 17:30 | 千问录音逐字稿 txt | runbook：agenticOps `projects/multica_ops/runbooks/千问拉取.md`（=description 双写）；落库走 docness 4c + 路由 | **运行中**（agent `3479ad7a` → oyun runtime `6550fa62`，playwright + chromium headless，venv `/opt/prjs/qianwen-venv`，2026-10-17 注册，2026-10-18 迁 oyun #217） |
| 腾讯会议拉取 | `21b9eca7` | 工作日 11:30 / 16:30 | 逐字稿 | runbook：agenticOps `projects/multica_ops/runbooks/腾讯会议采集.md`；落库走 docness 4c + 路由 | **运行中**（agent `f754fd3e` → oyun runtime `6550fa62`，agent 内联 tencent-meeting MCP + Token；projects-map 为 oyun 侧同步副本，2026-10-17 注册） |
| 待分类池分拣台 | `78e1a046` | 工作日 9–19 点每小时 :23 | —（消费上面三条的池产物） | runbook：agenticOps `projects/multica_ops/runbooks/分拣台.md`；向飞书「分拣台」群发单，解析用户回复执行 docness 归位三件套 | **运行中**（agent `077cd074` → oyun runtime `6550fa62`，lark-cli bot 发消息；2026-10-17 注册） |

补充事实：ZCode 客户端另有一条旧「飞书会话采集」自动化（prompt 存档
`.scratch/qianwen-minutes-sync/references/imness-automation-prompt.md`），已 paused，现役以 multica 侧为准。

## 家族统一原则

- **工作日判断**：一律 timor.tech API（type 0/4 执行，1/2/3 跳过），API 失败 fallback cron 周一至周五
- **错峰**：半点/半点偏移起跑（10:30 千问、11:30 腾讯会议），避开飞书采集整点体系；注册时以此为准
- **运行报告**：固定结构（新增 N / 自动入库 N₁ / 待分类 N₂ / 失败 N₃、判定明细表、
  凭据探活状态）；待分类池积压 > 5 → 显式警告行
- **凭据失效即停**：Cookie/Token 失效只报告不重试不改文件，等人工续
- **编排与核心分离**：prompt 只做编排/判定/报告，重活在脚本或 MCP 工具里，均可独立手跑

## 注册与监控（2026-10-17 已完成注册）

- 控制面：oyun 本地自托管 multica 实例（workspace 灵畿广东 `755b610f`，项目 AgenticOps `c51d250c`）；
  Mac 侧经 `multica --profile oyun`（或默认 config.json，已从 470 切到本实例，旧配置存 `config.json.470.bak`）直管
- runbook 双写约定：改 runbook 后必须 `multica --profile oyun autopilot update <id> --description "$(cat runbook.md)"`
- 两条新任务已登记 `agenticOps/docs/调度清单.md`（唯一事实源）与
  `agenticOps/projects/networking_ops/sched-audit.sh`（check_age 阈值 108000s≈30h，工作日节奏周末断档自然容忍）
- 千问拉取执行机是 oyun：playwright + chromium headless（#217 已从 Mac ego-browser 迁至 oyun）；venv `/opt/prjs/qianwen-venv`
- 腾讯会议拉取执行机是 oyun：HTTP MCP 无浏览器依赖；Token 内联在 agent 配置（secret 不落 runbook）
