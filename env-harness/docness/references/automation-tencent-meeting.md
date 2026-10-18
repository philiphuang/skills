# 腾讯会议定时采集（multica autopilot）

> 2026-10-17 用户裁定：腾讯会议采集做成定时任务，与千问拉取、飞书采集、笔记同步同放 multica。
> 采集物为**智能纪要**（docness collect SOP 4c：腾讯会议收纪要；逐字稿源属飞书妙记/千问）。
> 项目归属判定、待分类池、三件套入库与千问完全同构（见 `project-routing.md`）。

## 注册参数

| 项 | 值 |
|----|----|
| 载体 | multica autopilot |
| 节奏 | 工作日每日 2 轮：11:30 / 16:30（错开千问 10:30/17:30 与飞书采集整点体系） |
| 前置 | `TENCENT_MEETING_TOKEN`（https://meeting.tencent.com/ai-skill 获取）在 multica agent 环境可用；skill：`tencent-meeting-mcp`（本仓库 `.claude/skills/`） |
| 水位 | `/p/2606国际公司MCloud/.scratch/tencent-meeting-sync/state.json`（ended 会议 API 无增量游标，自维护：`last_run` + 已处理 `meeting_ids[]`） |

## Prompt 原文（注册时粘贴此节）

你是腾讯会议纪要采集 agent（无人值守）。执行以下操作：

0. **先判断今天是否工作日**：
   - 用 WebFetch 查询 http://timor.tech/api/holiday/info/$TODAY （$TODAY 替换为当天日期 YYYY-MM-DD）
   - type.type 为 0（工作日）或 4（调休补班）→ 继续执行步骤 1-7
   - type.type 为 1/2/3（休息日）→ 输出「今天是休息日，跳过采集」并结束
   - API 失败 → fallback 按周一至周五执行（周末跳过）

1. 先调用 `convert_timestamp`（不传参数）获取当前北京时间基准；再按水位文件
   `/p/2606国际公司MCloud/.scratch/tencent-meeting-sync/state.json` 的 `last_run` 确定查询窗口
   （首轮无水位 → 取 48h 窗口）；用 `convert_timestamp`（parse_time_str）换算窗口起止时间戳。

2. 调用 `get_user_ended_meetings(start_time, end_time)` 列窗口内已结束会议；
   对照水位文件 `meeting_ids[]` 去重，剩余即本轮新增。空 → 输出「无新会议」并结束。

3. 对每场新增会议取纪要：
   - `get_records_list(meeting_id)` → `record_file_id`（无录制 → 记「无录制跳过」）
   - `get_smart_minutes(record_file_id)` → 智能纪要内容（为空/报错 → 记失败原因，不重试）
   - 全程遵守 tencent-meeting-mcp SKILL.md：时间戳一律经 `convert_timestamp` 换算，
     每个工具调用附 `_client_info`，展示返回中的 `X-Tc-Trace`/`rpcUuid`

4. 读 `~/.config/project-daimon/projects-map.yaml`，对每场会议按 **subject × keywords** 判定
   项目归属（规则见 docness `references/project-routing.md`：唯一命中 high / 多命中按映射序取首
   medium / 无命中待分类；只能从映射既有条目里选，不改映射）。

5. 落库（遵循 docness collect SOP 4c + project-routing.md）：
   - **high** → 命中项目的 `project_dir` 跑 docness `init_workspace`，纪要存为
     `知识库/会议纪要/{yymmdd}-{主题}-纪要.md`（`{yymmdd}`=会议开始日期，`{主题}`=subject，
     清洗文件名非法字符；收件箱留同名副本），三件套：front matter
     （source=`tencent-meeting://meeting_id=<id>;code=<meeting_code>`、source_type=`tencent-meeting`、
     category 固定 `会议纪要`、original_filename=`smart_minutes_<meeting_code>.md`）+
     索引登记该项目 `docness-index.yml` + 日志记该项目 `.logs/`
   - **medium / 待分类** → 落待分类池 `/p/2606国际公司MCloud/收件箱/待分类/`
     （同名规范落盘，front matter `status: pending` + 判定依据字段
     `title`/`date`/`matched`/`suggested`——分拣单靠它们给用户出选项；
     仅记默认工作区 `.logs/`；归位时再登目标项目索引）
   - 归位主通道 = multica 分拣台 autopilot（工作日每小时向飞书「分拣台」群发分拣单，
     用户回复认领；见 docness `references/scheduled-collections.md`）

6. 更新水位文件：`last_run`=本轮开始时间，把本轮处理过的 meeting_id 追加进 `meeting_ids[]`
   （数组只保留最近 500 条防膨胀）。

7. 运行报告（固定结构）：新增会议 N（自动入库 N₁ / 待分类 N₂ / 失败或跳过 N₃）、
   判定明细表（主题 | 项目 | 命中词 | 置信）、待分类池当前清单、Token 探活状态；
   待分类池积压 > 5 → 追加显式警告行。

## 失败语义

- Token 失效（鉴权失败）→ 原样报告并结束，不重试不改文件，等人工到 ai-skill 页重取 Token
- 单场会议取件失败不影响其余：记录原因继续下一场
