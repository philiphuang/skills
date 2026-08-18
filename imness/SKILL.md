---
name: imness
description: 飞书 IM 会话与会议采集加工器。采集飞书群聊/单聊消息和会议妙记（含妙记结构化产物），打码脱敏后构建可自维护的 markdown 知识库，并提取候选任务供人工 triage。触发词：采集、拉取、会话、群聊、单聊、会议、妙记、纪要、待办、知识库、报告、巡检、整理。不负责：调度层(cron/编排)、非飞书源(微信/email)、跨项目分发、向他人自动派发任务。
version: 1.0.0
metadata:
  mode: production
  platform: opencode
  license: MIT
  requires:
    bins: ["lark-cli", "python3"]
    skills:
      # hard: 采集必备——提供 lark-cli 的 +命令 语义清单
      - name: "lark-im"
        source: "larksuite/cli (lark skill)"
        role: "会话采集——提供 +feed-group-list / +feed-group-list-item / +chat-messages-list 动作"
        required: true
      - name: "lark-minutes"
        source: "larksuite/cli (lark skill)"
        role: "会议妙记采集——提供 +detail 动作拉结构化产物"
        required: true
      - name: "lark-shared"
        source: "larksuite/cli (lark skill)"
        role: "lark-im/lark-minutes 的前置依赖——认证与权限处理"
        required: true
      # hard: 知识库 ingest 引擎
      - name: "llm-wiki"
        source: "sdyckjq-lab/llm-wiki-skill"
        runtime_path: ".claude/skills/llm-wiki/"
        install: "bash .claude/skills/llm-wiki/install.sh --platform claude"
        role: "知识库 ingest 引擎——raw 文件经其 Step1 结构化分析 + Step2 页面生成写入 wiki/"
        required: true
      # soft: 报告发布与任务流转（可选，手动触发）
      - name: "md2feishu"
        role: "报告飞书镜像发布（--feishu 时提示调用）"
        required: false
      - name: "lark-doc"
        role: "报告飞书镜像发布（--feishu 备选）"
        required: false
      - name: "lark-task"
        role: "候选任务确认后手动新建/关闭飞书任务"
        required: false
  config: "config.yaml"
---

# imness — 飞书 IM harness

imness 是面向 IM 的 **harness** 手段（与面向 docs 的 docness 对齐），把飞书协作内容持续加工成知识库并产出候选任务。它是**能力 skill（capability）**：脚本 + 调用说明，不含调度层。

## 四阶段流水 + 文档路由

```
① 采集          ② 打码/归一化         ③ ingest          ④ 提取/报告
飞书会话消息   →   硬凭证打码        →   写入知识库    →   候选任务报告
飞书会议妙记       归一化 episodes       (sdyckjq)           (人工 triage 出口)

                      ═══ 文档路由链（群文档 → docness）═══
                      采集后扫消息 → 发现文档链接/附件 → router(三段判断)
                                                      → 通过 → pending-docs/(待审池)
                                                      → 不通过 → 记录跳过
                      人工审核 → accepted → docness(URL/附件下载→收录)
                               → rejected → 放弃
```

飞书任务是**第④阶段的处理出口**（手动新建/关闭），不是采集源。不做反向同步。

### ingest 如何工作（imness ↔ sdyckjq 协作）

> **前置**：需先安装 sdyckjq（即 llm-wiki skill）到项目本地——
> `bash .claude/skills/llm-wiki/install.sh --platform claude`（来自 [sdyckjq-lab/llm-wiki-skill](https://github.com/sdyckjq-lab/llm-wiki-skill)）。
> imness 只做采集+打码，知识库构建（去重/矛盾检测/页面生成）由 sdyckjq 负责。

imness 是 **sdyckjq 的飞书 adapter**——专注采集+打码。采集完的 raw 文件，喂给 sdyckjq 的 ingest 工作流：

```
raw/transcripts/*.md  →  sdyckjq ingest（Step1结构化分析 → Step2页面生成）
                           ↓
                      wiki/sources/    ← 素材摘要页（含候选任务段）
                      wiki/entities/   ← 实体页更新
                      wiki/topics/     ← 主题页更新
                      .wiki-cache.json ← SHA256 去重缓存
```

imness **不自建 ingest 逻辑**。采集后，按以下步骤触发 ingest：

**步骤 1 — 检测需要 ingest 的 raw 文件**：
```bash
# 从项目根执行（路径以 knowledge/ 开头）
cd /path/to/project
for f in knowledge/raw/transcripts/*.md knowledge/raw/meetings/*.md; do
  result=$(bash .claude/skills/llm-wiki/scripts/cache.sh check "$f" 2>&1 | grep -m1 '^HIT\|^MISS')
  case "$result" in
    HIT*)           ;;  # 跳过，文件未变
    MISS*)          echo "需要 ingest: $f ($result)" ;;
  esac
done
```
- `HIT` → 跳过
- `MISS:hash_changed` → 文件有新消息，需重新 ingest
- `MISS:no_entry` → 首次 ingest

**步骤 2 — ingest**（读取 `.claude/skills/llm-wiki/SKILL.md`「工作流 2：ingest」，**以下适配 imness 场景**）：

> ⚠️ **imness 对 sdyckjq（即 `.claude/skills/llm-wiki/`）ingest 工作流的适配**（不修改 sdyckjq 代码，这些是指令层面的调整）：

1. **跳过隐私自查**：sdyckjq 工作流 2 第 253 行要求「首次进入 ingest 必须执行隐私自查提示（y/n）」。imness 的 raw 文件已在采集层经 redact 打码（4 类硬凭证），不含明文密码/API Key/手机号/client_secret。**根据 sdyckjq 第 275 行的 batch-ingest 绕过规则**（"用户在当前对话里已经明确说过素材里没有敏感信息，直接开始，或者用户是在 batch-ingest 流程中已经在顶层确认过一次，AI 可以跳过这一步"），imness 场景等同于 batch-ingest——raw 文件已确认不含硬凭证，**直接跳过隐私自查提示**。

2. **跳过 source-registry 路由**：sdyckjq 的素材类型表（source-registry.tsv）只定义了 web_article/pdf/wechat 等 9 种来源，不认识「飞书会话归档」。imness 的 raw 文件**直接作为 local_document 类型进入 Step 1**，不调 source-registry.sh match-file。

3. **执行 Step 1 结构化分析** → 输出 JSON（entities/topics/connections/contradictions，含 confidence + evidence）
4. `bash .claude/skills/llm-wiki/scripts/validate-step1.sh` 验证 JSON
5. **Step 2 页面生成** → 写 source 页 + 更新实体/主题页 + index/log
6. `bash .claude/skills/llm-wiki/scripts/create-source-page.sh` 原子写 + 自动更新缓存

sdyckjq 的 cache.sh 按 raw 文件整体 SHA256 判断是否变化——增量采集追加新消息 → hash 变 → `MISS:hash_changed` → 重新 ingest。

**当前状态**：imness 的 collect/redact/report 已可运转，但 ingest 步骤需 agent 手动执行（验证通过：2026-08-01 仇模融群消息 → ingest → report 提取到新候选任务）。调度层（cron 自动触发 ingest）是独立 effort，不在本范围。

## config（多渠道多实例）

`config.yaml` 用 `channels.<渠道>[]` 结构组织（见 `config.example.yaml`）。飞书渠道下可配多个实例（同人多账号 / 不同人），每个实例 = 1 个 lark-cli profile，字段：`name` / `lark_profile` / `my_name` / `my_id` / `my_aliases[]` / `project_tags[]`（全必填）。微信渠道占位（采集未实现）。

**config.py 是 config 的唯一读取入口**（纯数据读取，不含 lark-cli 调用），common.sh / chat_tools.py / report.py 都调它，不内联 pyyaml。子命令：

| 命令 | 用途 |
|------|------|
| `config.py instances [--json]` | 列飞书渠道所有实例 |
| `config.py instance <name> [--field <f>]` | 取实例字段（如 project_tags / lark_profile） |
| `config.py my-aliases [<name>]` | 全局合并或单实例的 my_aliases（report 身份判定用） |

会议发现群查询（project_tags ∩ 「会议记录」标签）由 `common.sh` 的 `get_meeting_chats` 提供——标签匹配需要调 lark-cli，属于 lark-im skill 的接口调用，归位到 common.sh 而非 config.py。

**身份消费**（#23）：渠道是溯源标签不隔离——report auto_triage 全局合并所有实例 aliases；collect-chats 按当前实例 aliases 排除自己。raw 文件头加 `source_channel`/`source_instance` frontmatter 供 sdyckjq ingest 继承溯源。

## 能力脚本

6 个模块，契约如下（实现进度见各段落末尾）。

### router/ — 文档路由链（群文档 → docness）

群消息 → 发现文档 → 群重要性过滤 → AI 价值判断 → 待审池 → 人工审核 → docness 收录。

| 项 | 值 |
|---|---|
| 调用 | `python3 products/imness/router/scan_runner.py`（stdin 读 JSON 消息数组） |
| 判断维度 | 群重要性（`knowledge/mywork.config.md`）+ AI 判断文档类型和相关性 |
| 配置文件 | `knowledge/mywork.config.md`（人类可读写 MD，含群组重要性 + 当前工作清单） |
| 待审池 | `knowledge/pending-docs/{timestamp}-{id}.md`（YAML frontmatter + 上下文原文） |
| 日志 | `knowledge/router-log.jsonl`（每行一条决策 JSON） |
| 模块 | `decision.py`（数据模型）、`context_loader.py`（配置读取）、`route.py`（编排入口）、`verify.py`（验证）、`scan_runner.py`（CLI 入口） |

**全流程**:
```
# 阶段A: 扫描（自动）
echo '[...]' | python3 products/imness/router/scan_runner.py

# 阶段B: AI 判断 → 入待审池（agent 调 LLM 后执行）
from products.imness.router import finalize, write_pending
d = finalize(doc, ai_response)
write_pending(d)

# 人工审核
from products.imness.router import pending_list, review
pending_list()                        # 查看待审池
review("accepted", "file.md")         # 通过

# 阶段C: 收录
from products.imness.router import process_accepted, mark_processed
process_accepted()                    # 列出待收录，agent 据此调 docness
mark_processed("file.md")             # 标记完成
```

### collect-chats.sh — 会话采集（多实例）

遍历 config 所有飞书实例 → 每个实例切对应 lark profile → 遍历该实例 `project_tags` 标签 → `+feed-group-list-item` 列会话 → 按 chat_id 拉消息 → 归一化（含 redact 打码 + `source_channel`/`source_instance` frontmatter）→ 与已有 raw 文件去重合并（frontmatter 保留）→ 写 raw/transcripts。

| 项 | 值 |
|---|---|
| 调用 | `scripts/collect-chats.sh [--instance <name> \| --all \| --feed-id <chat_id> \| --dry-run]`（无参遍历所有实例） |
| 多实例 | 遍历 `channels.feishu[]`，每个实例切 `lark_profile`（EXIT trap 恢复原 profile），串行采集 |
| 标签路由 | 读 config 实例的 `project_tags` → 经 `config.py` → `lark-cli im +feed-group-list` 找 group_id（加群在飞书界面操作，零代码改动） |
| 身份 | `my_aliases`/`my_name` 经 `config.py` 读取，单聊辨认对方名时按实例排除自己 |
| 产出 | `knowledge/raw/transcripts/{显示名}_{chat_id前12位}_{YYYY-MM}.md`（bold-speaker 格式，每条消息带 `<!-- msg_id:xxx -->` 锚点 + 文件头 frontmatter，已打码）。`YYYY-MM` 为文件创建时的月份。兼容旧文件（无月份后缀，采集时自动识别）。 |
| 增量 | index 有 `last_message.create_time` → 带 `--start` 只拉新消息；否则全量。游标按实例隔离，存 `knowledge/index.json` 的 `chats[].last_message.create_time`（含 `chats[].instance` 区分多实例） |
| 去重 | 全量/增量拉取后统一按 msg_id 去重重写（幂等：飞书无新消息时文件不变）；合并时保留 frontmatter |
| 计数 | `chats[].message_count` 基于文件内 msg_id 锚点数（与归一化的 seen 口径一致） |
| 日志 | `knowledge/sync.log`（时间\|[实例]\|会话名\|模式\|+新增(总条数)\|耗时）；切割时追加 `SPLIT` 事件 |

**自动切割**: 单文件超过 `SPLIT_SIZE_KB`（默认 200）时，采集流程自动冻结当前文件（不再追写），新建 `{显示名}_{chat_id前12位}_{当前月份}.md` 承接后续消息。下次采集自动找到最新月份文件继续追写。切割事件记入 sync.log（`SPLIT \| {会话}: {旧大小}KB → {新文件名}`）。适用于大群聊（消息量持续增长），小私聊不会触发。
| 何时用 | 需要拉取/更新飞书群聊和单聊消息到本地时 |

**单聊处理**: chat_name 为空时扫历史消息辨认对方 display_name 并缓存（按当前实例 `my_aliases` 排除自己）。

**依赖**: `common.sh`（共享路径/日志函数 + `get_feed_group_id`，按实例取 project_tags）、`chat_tools.py`（归一化/去重/索引，均接收 `--instance`）、`config.py`（config 唯一读取入口）。

### collect-meetings.sh — 会议妙记采集（多实例）

遍历 config 所有飞书实例 → 每个实例用标签匹配找会议发现群 → 从这些群已采集的 raw transcript 提取妙记链接 → `lark-minutes +detail` 拉结构化产物 → 归一化（含 redact 打码 + source frontmatter）→ 写 raw/meetings。

| 项 | 值 |
|---|---|
| 调用 | `scripts/collect-meetings.sh [--instance <name> \| --dry-run]`（无参遍历所有实例） |
| 发现渠道 | **标签匹配**（#22）：同时具有「本实例 project_tags 任一」**和**「会议记录」标签的群 = 会议发现群（`config.py meeting-chats`）。不再用硬编码 chat_id |
| 前提 | 会议发现群需先经 collect-chats 采集到本地 transcript |
| 产出 | `knowledge/raw/meetings/{标题}_{token前12位}.md`（frontmatter → 标题→会议总结→待办→时间线→关键词，已打码） |
| 去重 | 按 minute_token 前 12 位（已采的跳过） |
| 何时用 | 需要归档飞书会议妙记（纪要/待办/章节）时 |

**前提**: 该群消息需先经 collect-chats 采集到本地。会议采集复用会话扫消息管线，不单独拉取。

**结构化字段**（妙记链路独有）: `artifacts.{summary(str), todos[](content/is_done/todo_id), chapters[](start_ms/stop_ms/title/summary_content), keywords[]}`。飞书无 vc 一条龙，这些字段只在妙记链路。附件不下载，只记引用。

**可消费性**: todos 进「待办」区（带 `<!-- todo_id:xxx -->` 锚点），chapters 进「时间线」区（带时段），供下游 ingest 和 report 消费。

### redact.py — 打码

采集层在写 raw 前执行，raw 永远只有打码版。覆盖 4 类硬凭证，只挡硬凭证不挡客户名/代号/手机号主体。

| 项 | 值 |
|---|---|
| 调用 | `python3 scripts/redact.py`（stdin→stdout）或 `from redact import redact; redact(text)` |
| 何时用 | collect 脚本写 raw 前；任何要把飞书内容落 git 前的安全过滤 |
| 测试 | `python3 imness/scripts/test_redact.py`（26 用例，4 类正反例 + 幂等 + 混合） |

**打码边界**（详细正则见 `scripts/redact.py`，运行 `test_redact.py` 看真实样例）:
- 密码（`pw:`/`passwd:`/`password:`/`密码:` 后 token，中英文冒号都匹配）→ `[REDACTED]`
- API Key 哈希（40+ 位连续小写十六进制）→ `[REDACTED-HASH]`
- 手机号（1[3-9] 开头 11 位，前后非字母数字）→ 保留前3后4（`178****8135`）
- IBOSS client_secret → `[REDACTED]`

**幂等**: 打码后再过一次不变（手机号含 `****` 不再匹配，其余类替换为固定串）。

**接受**: 打码不可逆，漏网不主动发现（个人 repo + 无原始版兜底）。

### report.py — 候选任务提取 + 报告

三来源提取候选任务 → 去重合并（累积 sources）→ 本地 MD 报告 + 飞书镜像发布提示。

| 项 | 值 |
|---|---|
| 调用 | `python3 imness/scripts/report.py [--feishu]` |
| 来源 1 | `raw/meetings/*.md` 的「## 待办」段（带 todo_id 锚点，置信度 `EXTRACTED`） |
| 来源 2 | `wiki/topics/*.md` 的「## 待办」段（置信度 `INFERRED`） |
| 来源 3 | `wiki/synthesis/sessions/*.md` 的结晶任务（置信度 `INFERRED`） |
| 来源 4 | `wiki/sources/*.md` 的「## 候选任务」段（sdyckjq ingest 产出，置信度 `EXTRACTED`）— **imness ↔ sdyckjq 协作的关键断点** |
| 产出 | `reports/{date}-candidate-tasks.md`（按 topic 分组 + 待澄清区） |
| 飞书镜像 | `--feishu` 输出发布提示，实际发布由 `/md2feishu` 或 `/lark-doc` skill 完成（手动触发，单向只读） |
| 去重 | todo_id 优先；否则 content 前 40 字符归一化。同任务合并累积 sources |
| 候选字段 | content / assignee（@负责人，可空）/ confidence / topic_slug / sources[] |
| 置信度 | `EXTRACTED`（会议明确 todo / source 页 ingest 产出）/ `INFERRED`（wiki 推断）/ 待澄清区（无负责人且非 EXTRACTED） |
| 何时用 | 需要从飞书对话/会议里提取待办、生成候选任务报告时 |

**分诊逻辑**: 有明确负责人的进 topic 分组区；无负责人且非 EXTRACTED 的进「待澄清」区。身份判定（is_mine）全局合并 config 所有渠道所有实例的 `my_aliases` + `my_id`（经 `config.py`），不按来源实例判定。

### maintain.sh — 自维护（定期巡检层）

知识库健康检查：孤立页 / 断链 / 过时 / frontmatter 完整性 / 置信度标签分布。置信度高的问题自动修复（孤立页补入 index.md），低的列入报告待人工。

| 项 | 值 |
|---|---|
| 调用 | `scripts/maintain.sh`（手动触发；调度自动化另议，spec Out of Scope） |
| 产出 | `reports/{date}-maintenance.md`（断链/过时/frontmatter 问题待人工） |
| 检查项 | 孤立页（排除 sources 叶子页）/ 断链 / 过时（>90天）/ frontmatter / 置信度标签 |
| 自动修复 | 孤立页补链接到 `knowledge/index.md`（幂等，已存在则跳过） |
| 何时用 | 知识库健康巡检、ingest 后定期检查、发现矛盾/孤立页/断链时 |

**注意**: sdyckjq skill 自带的 `lint-runner.sh` 依赖 monorepo packages，跨项目不可用。imness maintain 自建轻量 lint（移植核心检查 + 置信度标签统计），不依赖已归档 skill。

### 自维护三层（指令）

1. **写入时**（sdyckjq ingest 自带）：去重（SHA256 缓存）、矛盾检测、关联连边 —— 由 ingest 流程负责，imness 不重复实现。
2. **查询时动态整理**（agent 自主行为）：你回答用户问题时，若发现知识库局部过时/矛盾/碎片化，**当场重写 compiled_truth、降权旧结论（标 `[过时]`）、补缺失交叉引用，patch 回库**。无需显式指令；回答里简要说明「整理了 X（发现 Y 已过时）」。
3. **定期后台**（maintain.sh）：本脚本。置信度高自动修复，低的人工报告。

**过期策略**: 只降权（置信度标签 + 正文标注「已被取代」）不删，git 保留历史。

## 知识库结构（sdyckjq 骨架，已就位）

```
knowledge/
├── raw/transcripts/    会话原始对话（打码版，进 git）
├── raw/meetings/       会议妙记产物（打码版）
├── mywork.config.md    路由策略配置（群重要性+当前工作清单）
├── pending-docs/        待审池（路由通过的文档等人工审核）
├── router-log.jsonl     路由决策日志
├── wiki/topics/        主题页：compiled_truth（rewrite-not-append）+ timeline（append-only 带溯源）
├── wiki/entities/      实体页：人物/概念
├── wiki/sources/       素材摘要：每个 ingest 过的 transcript 对应一页
├── wiki/synthesis/     对话结晶：关键会议决策沉淀
├── index.json          采集增量游标
├── purpose.md          研究方向
├── .wiki-schema.md     知识库 schema
└── .wiki-cache.json    SHA256 去重缓存
```

**置信度标签**（与 sdyckjq 体系对齐）: `[事实]`/EXTRACTED（可溯源） · `[推断]`/INFERRED（综合） · `[待核]`/AMBIGUOUS（单源/模糊） · `[过时]`/UNVERIFIED（已被取代）。

## 任务流转

候选任务落 `inbox/飞书/` 原地 triage（改文件状态标记，不搬家）。确认后手动对接 `lark-task` 新建/关闭，任务 ID 回填 inbox 文件。wayfinder 是 triage 的一种方法，不绑死。

## 术语

详见 `CONTEXT.md`（项目根）的领域术语表：harness / imness / docness / feed group / 打码 / 硬凭证 / 四阶段流水 / inbox / compiled_truth / timeline / triage。
