# 定时拉取编排（multica autopilot，v2）

> 2026-10-17 用户裁定：千问定时任务与「拉取飞书消息」（multica:飞书采集）、
> 「拉取微信文档收藏」（multica:notehelper-sync 笔记同步）**同放 multica**——
> 取代 #110 的「ZCode 客户端并列新建」决策（v1 prompt 存档
> `.scratch/qianwen-minutes-sync/references/qianwen-sync-automation-prompt.md` 仅作历史）。
> 本文件是 v2 定时编排的规范唯一事实源；getter 本体仍零调度（#205 边界不变，编排属调用方）。

## 注册参数

| 项 | 值 |
|----|----|
| 载体 | multica autopilot（与 飞书采集 `e94fa6e4`、notehelper-sync 同体系） |
| 节奏 | 工作日每日 2 轮：10:30 / 17:30（半点，错开飞书采集整点体系） |
| 工作日判断 | timor.tech API（见 prompt 步骤 0），fallback cron 周一至周五 |
| 运行现场 | 只读 skills-factory scripts/；产物落各项目工作区与待分类池 |

注册需 `multica login`（2026-10-17 时本机会话已过期）。注册后把新任务 id 补进
`/p/agenticOps/projects/networking_ops/sched-audit.sh` 的 check_age 清单
（标签建议 `multica:千问拉取(工作日 10:30/17:30)`，阈值约 30h）。

## Prompt 原文（注册时粘贴此节）

你是 qianwen 千问录音拉取 agent（v2 getter 编排，无人值守）。执行以下操作：

0. **先判断今天是否工作日**：
   - 用 WebFetch 查询 http://timor.tech/api/holiday/info/$TODAY （$TODAY 替换为当天日期 YYYY-MM-DD）
   - type.type 为 0（工作日）或 4（调休补班）→ 继续执行步骤 1-6
   - type.type 为 1/2/3（休息日）→ 输出「今天是休息日，跳过拉取」并结束
   - API 失败 → fallback 按周一至周五执行（周末跳过）

1. cd /p/skills-factory/products/qianwen-minutes-sync/scripts，运行增量列会话：
   `python3 -m qianwen_sync.run list-new > /tmp/qianwen-new.jsonl`
   - 文件为空 → 输出「无新会话」并结束
   - 退出码非 0 / 报 Cookie 失效 → 原样报告失效信息并结束（不重试、不改任何文件，等人工续 Cookie）

2. 读 `~/.config/project-daimon/projects-map.yaml`，对 /tmp/qianwen-new.jsonl 每条按
   **标题 × keywords** 判定项目归属（规则见 docness `references/project-routing.md`）：
   - 唯一命中 → `high`（建议该项目）
   - 多条目命中 → 按映射文件顺序取首，`medium`
   - 无命中 → `待分类`
   - 只能从映射既有条目里选，不能创造新目标；不改映射文件

3. 逐个**串行** fetch（单会话 90s 超时，失败不重试，记录原因后继续下一个）：
   `python3 -m qianwen_sync.run fetch <会话ID> --out /tmp/qianwen-fetch/{yymmdd}-{主题}-逐字稿.txt`
   （`{yymmdd}` 取该条 create_time 日期，`{主题}` 取 title 去掉「录音纪要：」前缀；清洗文件名非法字符）

4. 落库（遵循 docness collect SOP 4c 千问分支）：
   - **high** → 命中项目的 `project_dir` 跑 docness `init_workspace`，逐字稿复制进其
     `收件箱/` 与 `知识库/会议纪要/`，执行入库三件套（front matter：source=chat URL、
     source_type=`qianwen-audio`、category 固定 `会议纪要`、original_filename=导出文件名；
     索引登记该项目 `docness-index.yml`；日志记该项目 `.logs/`）
   - **medium / 待分类** → 落待分类池 `/p/2606国际公司MCloud/收件箱/待分类/`（同名规范落盘，
     front matter `status: pending` + 判定依据字段 `title`/`date`/`matched`/`suggested`
     ——分拣单靠它们给用户出选项；仅记默认工作区 `.logs/`；不登索引——归位时再登目标项目）
   - 归位主通道 = multica 分拣台 autopilot（工作日每小时向飞书「分拣台」群发分拣单，
     用户回 `编号 项目名`/`编号 跳过` 认领；见 docness `references/scheduled-collections.md`）；
     交互会话可现场认领（流程同 docness project-routing.md「待分类池」节）；
     池按来源通用，分拣维度是分类目录如 会议纪要/，不按千问建目录）

5. 清理 /tmp/qianwen-fetch/ 与 /tmp/qianwen-new.jsonl

6. 运行报告（固定结构）：新会话 N（自动入库 N₁ / 待分类 N₂ / 失败 N₃）、判定明细表
   （标题 | 项目 | 命中词 | 置信）、待分类池当前清单、Cookie 探活状态；
   待分类池积压 > 5 → 追加显式警告行
