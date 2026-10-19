---
name: qianwen-minutes-sync
description: 千问录音逐字稿纯获取工具（v2 getter，agent 中立）。list-new——Cookie 快照通道增量列出新录音会话（JSONL，输出即推游标）；fetch——浏览器通道导出会话官方原文 txt（退出码语义化：登录失效/会话不存在/无导出入口）。零存储零分类零调度，落库由 docness collect 承担。另含 gen-projects-map 项目映射表生成；v1 拉取/分类/归档管线为遗留命令（run/finalize）。
---

# qianwen-minutes-sync

千问录音的**逐字稿获取**工具集。v2 主路径 = 纯 getter（`list-new` + `fetch`，规范 `references/getter-spec.md`，地图 #202 / 定形 #205 / 实现 #206）：
只负责列会话和导出官方原文 txt，不做存储/分类/调度；编排消费方是 docness collect（其 `sops/collect.md` 4c 千问分支），也可被任何 agent 直接手跑。
定时编排 = **multica autopilot**（与飞书采集、笔记同步/微信收藏拉取同体系，2026-10-17 裁定），
prompt 与注册参数见 `references/automation-multica.md`。

## v2 getter：list-new / fetch

### 前置

- **list-new 通道**：Cookie 快照（`~/.config/project-daimon/qianwen-cookie.txt`，或 `--cookie` / 环境变量 `QIANWEN_COOKIE`）——会话列表 API 只验 Cookie
- **fetch 通道**：浏览器导出（转写正文在 AWSC 验签墙后，浏览器是唯一通道，#203 定论；txt 导出为前端本地 Blob，非网络接口）。自动分发：**playwright + chromium headless 优先**（Linux/oyun，#217 迁移；Cookie 从快照注入），未装 playwright 的 Mac 回退 ego-browser（人工登录态）

### 调用（在 `scripts/` 目录下）

```bash
# 增量列新会话：JSONL {id,title,create_time,updated_at}；打印完即写游标
python3 -m qianwen_sync.run list-new [--state <state.json>] [--reset]

# 导出官方原文 txt（[mm:ss] 发言人N: 文本），输出一行结果 JSON
python3 -m qianwen_sync.run fetch <会话ID或qianwen.com/chat URL> [--out <路径>] [--timeout 90] [--cookie <原始Cookie头>]
```

### fetch 退出码（调用方分支依据）

| 码 | 含义 | 处置 |
|----|------|------|
| 0 | 成功（JSON 含 path/bytes/title） | 收文件 |
| 1 | 其他错误（ref 非法/浏览器通道不可用/超时） | 看错误行 |
| 2 | 登录失效 | 人工续 Cookie 快照（playwright）或重登 ego-browser |
| 3 | 会话不存在/非录音会话 | 跳过记录 |
| 4 | 无导出入口 | 站点改版嫌疑，人工看页面 |

纪律：单会话一次浏览器会话 90s 超时，失败不自动重试；批量场景由调用方串行逐个 fetch。完整契约见 `references/getter-spec.md`。

## gen-projects-map：生成通用项目映射表

### 用途

提供一个项目根目录（如 `/opt/prjs`），扫描其中的一级子目录，识别项目，生成或合并**通用项目映射表** `projects-map.yaml`（项目 → 归档目录/识别关键词）。该映射是跨工具的通用配置，归 **project-daimon 命名空间**；千问纪要同步管线（#111）是消费方之一，按它把新纪要分类归档。

### 调用

```bash
python3 products/qianwen-minutes-sync/scripts/gen_projects_map.py \
  --dir /opt/prjs \
  [--out <输出路径>]      # 默认 ~/.config/project-daimon/projects-map.yaml
  [--init-from <种子文件>] # 输出不存在时用种子配置打底（如仓库示例模板）
  [--dry-run]             # 只打印报告，不写文件
```

### 配置保存在用户命名空间

输出默认落在 `~/.config/project-daimon/projects-map.yaml`——**用户空间，不在 skill/仓库空间**。仓库内 `assets/projects-map.example.yaml` 仅作示例模板（首次生成可用 `--init-from` 打底）。

### 项目识别规则

满足其一即视为项目目录：

- 目录名以两位以上数字开头（编号项目，如 `2607科创平台`、`24 05 卓语平台`）
- 含工作台类标记（`工作台/收件箱/发件箱/知识库/归档/工作法` 之一，或 `AGENTS.md`/`CLAUDE.md`）

### 合并语义（重跑安全）

- 按唯一键 `project_dir` 合并：**已存在条目的 id/keywords/archive_dir 一律保留**（手工编辑不被覆盖）
- 新发现目录追加为草稿条目（note 标 auto，keywords 为目录名+子目录名草拟，需人工校订）
- 目录已消失的条目不删除，报告里提示人工处理
- 顶层 `exclude:` 名单（目录名列表）可永久排除工具目录，收录后手工挪入即可

### 注意

重新生成会重写文件注释；需要长期保留的说明请写进条目的 `note` 字段。

### 配置格式

见 `assets/projects-map.example.yaml`：`defaults.inbox_dir`（待分拣收件箱）、每条目的 `keywords`（标题匹配）与 `archive_dir`（归档目录；为空则落待分拣）。归档目录/命名/front-matter/schema 规范已由 #108 锁定，见 `references/archive-spec.md`。

## v1 遗留管线（run / finalize）

拉取→分类→归档的完整管线（#103/#111 落地）保留为遗留命令，仅维护不再演进；规范见
`references/archive-spec.md`（#108）、`classification-spec.md`（#109）、`run-spec.md`（#110，含 ZCode 自动化 prompt 存档说明）。
v2 已取代其主路径地位：逐字稿获取走 getter，落库走 docness。
