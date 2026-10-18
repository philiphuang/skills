# 会议录音的项目归属判定与确认

> 会议来源横跨项目（科创平台、AI Hub、工单智能体……），而工作区按项目解析——
> **入库前必须先定项目**，否则会落错知识库（2026-10-16 实测：研发审核一条误落 MCloud，人工迁回科创平台）。
> **分拣维度是 docness 分类目录（会议纪要/技术资料/…），不是来源工具**（千问/腾讯会议/妙记只是
> source_type 标记，不构成目录维度）。

## 映射事实源

`~/.config/project-daimon/projects-map.yaml`（project-daimon 命名空间，用户空间配置）：

- 条目字段：`id` / `name` / `project_dir` / `keywords`（人工维护；
  `qianwen-minutes-sync` 的 `gen_projects_map.py --dir <项目根>` 生成草稿并合并手工编辑）
- **不自动改映射**：改判、补关键词属人工维护动作，agent 只建议不代写

## 判定规则（确定性关键词，语义同 qianwen-minutes-sync v1 classification-spec 第一段）

| 情形 | 判定 |
|------|------|
| 标题含**唯一**条目的关键词 | 建议该条目，置信 high |
| 标题命中**多条目** | 按映射文件顺序取首，置信 medium（标注「多命中」） |
| 无命中 | 待分类，交用户指定 |

- 匹配对象是**会议标题**（list-new 的 `title` / 腾讯会议的 `subject`）
- agent/LLM 只能从映射既有条目里选，**不能创造新归档目标**

## 确认流程（判定在先，人在最后）

1. 列出新增会议清单（千问 `list-new` / 腾讯会议 ended 列表）
2. 逐条按上表判定，生成**判定表**：

   | 会议标题 | 建议项目 | 命中词 | 置信 |
   |---------|---------|--------|------|

3. **判定表交用户确认**——确认 / 改判 / 跳过，逐条过；交互会话（Claude Code）用
   **结构化选择卡**（AskUserQuestion）逐条出卡，不贴纯文本表格：选项 = 建议项目（标推荐）/
   其余映射条目 / 跳过
4. 确认后才拉取 + 入库（不做先斩后奏的批量拉取）
5. 用户改判且理由可归纳为标题关键词缺失 → **建议**把新关键词补进 projects-map（用户自己改或明示让改）

免确认情形：用户指令里已明确项目（如「拉科创平台最新的录音」），直接执行。

无人值守（multica 定时拉取，见 `references/scheduled-collections.md`）无法交互确认：
唯一命中（high）自动入库；多命中（medium）与无命中**照常拉取后落待分类池**，
判定明细写进运行报告，人下轮认领（认领通道见下「待分类池」）。

## 待分类池（文件即状态，通用池）

- **池位置**：`{$默认工作区}/收件箱/待分类/`（= projects-map `defaults.inbox_dir`，
  当前 `/p/2606国际公司MCloud/收件箱/待分类`）——**跨项目、跨来源共用一个池**
  （千问/腾讯会议/妙记等来源共用；来源差异只体现在 front matter 的 `source_type`，不体现为目录）
- **落池形态**：规范名按来源产物（千问 `{yymmdd}-{主题}-逐字稿.txt`、腾讯会议
  `{yymmdd}-{主题}-纪要.md`；拉取时即按会议日期+标题定名，归位时零重命名），
  front matter 记 source / `source_type`（qianwen-audio /
  tencent-meeting / feishu-minutes）/ category=`会议纪要` / **`status: pending`**
  / **判定依据字段（分拣单靠它们给用户出选项）**：`title`=原始标题、`date`=会议日期
  YYYY-MM-DD、`matched`=命中关键词（无命中留空）、`suggested`=medium 建议项目 name（无则留空）
- **归位流程**（用户认领后）：
  - **主通道（无人值守产物）= 飞书「分拣台」群回复认领**：multica 分拣台 autopilot
    （工作日每小时，见 `references/scheduled-collections.md`）向群发分拣单（编号+文件名+可选项目），
    用户在群里回 `编号 项目名` 或 `编号 跳过`，下一轮解析执行归位并群内回执；
    群消息由 lark-cli bot 身份发（用户身份缺 `im:message.send_as_user` scope），
    解析时只认用户本人消息
  - **交互会话**：用户在场时也可现场认领，直接走下方步骤
  - 步骤：确认项目 → 该项目 `init_workspace` → 移入其
    `收件箱/` + `知识库/会议纪要/` → 三件套（`status: collected`）→ 两侧 `.logs` 记迁移 →
    可建议回写 keywords
- 池内积压 > 5 → 报告加显式警告行（抄 v1 classification-spec 提醒语义）

## 入库落点

确认的项目以其 `project_dir` 跑 `init_workspace` 解析该项目工作区
（收件箱 / 知识库 / logs），三件套（front matter / 索引 / 日志）全部落**该项目**，
不得落 agent 当前所在项目。

## 适用范围

- 各会议来源（千问录音 / 腾讯会议 / 飞书妙记）的批量与单条收录均适用
- 任何个人级跨项目内容源同理
