# 千问纪要归档规范（#108 锁定，2026-10-03）

> ⚠️ **遗留（v1）**：本规范服务于 v1 管线（run/finalize）。主路径已由 v2 getter（`list-new`/`fetch`，见 `getter-spec.md`，#202/#205/#206）取代——v2 零存储零分类，落库由 docness 承担；本文件仅在运行 v1 遗留命令时有效。

本文件是 qianwen-minutes-sync 管线归档规范的唯一事实源，#111 实现按此消费。
决策过程见 issue #108；上游地图 #103。

## 1. 目录体系

- **中转目录**：`/opt/prjs/2606国际公司MCloud/.scratch/qianwen-minutes-sync/`
  纯机器临时区，分类完成后即清，人工无需关注。
- **待分拣收件箱**：`/opt/prjs/2606国际公司MCloud/收件箱/qianwen-待分拣`
  模糊归属纪要的人工入口；与 projects-map `defaults.inbox_dir` 保持一致。
- **归档目录（项目内，双形态）**：项目内有 `归档/` → `归档/纪要/`；否则 → `纪要/`。
  显式写在 projects-map 条目 `archive_dir`，消费方不再推导。
  归档目录内部结构由各项目自治，管线不干预。

## 2. 文件命名

```
<YYYY-MM-DD>-<标题清洗截断40字>-<conversation_id前12位>.md
```

- 日期 = 录音/会话时间（conversation `create_time`），非拉取时间
- 标题清洗：去除 `/\:*?"<>|` 等非法字符，空白折叠为单个空格，截 40 字
- **文件名即状态**：目标路径已存在同名文件 → 跳过（#105 先例；与 imness `YYYY-MM-DD-{chat|meeting}-主题.md` 命名风格一致）

## 3. front-matter

docness 8 字段原样（对齐 `src/docness` 规范，产物即合法 docness 文档），管线元数据放独立顶层键 `qianwen:`，不污染 docness：

```yaml
---
docness:
  source: https://qianwen.com/chat/<conversation_id>?entry=audio_qianwen
  source_type: qianwen-audio          # docness 侧词表需增补此枚举（#111 实现时同步）
  imported_at: '<拉取时间 ISO 8601 带时区>'
  knowledge_category: 会议纪要
  original_filename: <同文件名>
  status: collected
  processing: []
  published: []
qianwen:
  conversation_id: <完整 32 位 id>
  recorded_at: '<会议时间 = conversation create_time，ISO 8601>'
  speakers: []                        # 可选；API 无独立参会人字段，说话人标签混在
                                      # transcription 正文，是否有真名未验证 → #111 验证后填
  classification:
    project: <projects-map 条目 id>
    matched_keyword: <命中的关键词>
    confidence: high|medium|low       # 取值语义归 #109 决策票
---
```

## 4. projects-map schema v1（锁定）

扁平结构，不嵌套：

- 顶层：`version: 1`、`exclude: [目录名…]`、`defaults: {inbox_dir, match: title}`、`projects: [...]`
- 条目：`id`、`name`、`project_dir`、`archive_dir`（空 → 待分拣）、`keywords[]`、`note?`
- 可选扩展（非 breaking）：`description`（一句话描述，辅助 #109 消歧）、`domain`（工作域归属）
- 匹配规则 v1：仅匹配纪要标题；按文件顺序取首个命中；正文匹配与否由 #109 定

## 5. 维护流程

- **映射是唯一的分类事实源，管线永不猜**
- 新项目启动 → 重跑 `gen_projects_map`（或手工加条目）并校订关键词，再让管线消费
- 待分拣积压 → 人工补映射/校关键词后重跑管线归档
- 条目只改 `~/.config/project-daimon/projects-map.yaml`；仓库示例模板不追随日常变动
