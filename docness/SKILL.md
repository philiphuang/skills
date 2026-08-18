---
name: docness
description: 文档收发编排器。把各来源文档（URL/本地/腾讯文档/飞书/会议录音）收进来转为 Markdown 入知识库，或从 Markdown 生成配图/PPT/Word/PDF 并推送到飞书/腾讯文档。用户要收集/归档文档、配图/转格式、或推送/上传文档时使用。
license: MIT
metadata:
  version: "1.2.1"
  mode: production
  platform: opencode
---

# Docness

## 核心逻辑

任何来源的文档收进来 → 复杂度判定后转 Markdown → 汇入知识库 → 按需交付（配图/PPT/Word/PDF/飞书/腾讯文档）。转换工具链：

```
输入文件 → complexity.py → simple → pandoc / pypdf / pandas+openpyxl → Markdown
                          → complex → MinerU Skill → 高精度 Markdown
                          （simple 失败自动升级 complex）
反向: pandoc MD→PDF/DOCX/PPTX, pandas CSV→XLSX
旧格式(.doc/.ppt/.xls/.wps): LibreOffice headless → 新格式 → 继续
```

## 三条 SOP

| SOP | 职责 |
|-----|------|
| **收文件** | URL/本地文件 → 获取 → 复杂度判定 → 路由转换 → 分类保存 |
| **处理** | Markdown → 配图 / 转 Word / 转 PDF / 生成 PPT |
| **发送** | Markdown/成品 → 上传到飞书/腾讯文档 |

## 触发规则

- 裸 URL 或本地路径 → 默认执行 collect SOP
- 带触发词 → 触发词决定 SOP
- Markdown URL/路径 + 无其他意图 → 默认 send 意图

触发词权威清单见 `scripts/dispatch.py`（`COLLECT_TRIGGERS` / `PROCESS_TRIGGERS` / `SEND_TRIGGERS`），各 SOP 详见 `sops/collect.md`、`sops/process.md`、`sops/send.md`。

## 工作区结构

> 工作区目录归属**项目**而非 skill 自身，实际路径由项目配置决定（见下文「前置条件与初始化」）。
> 以下为默认结构：

```
收件箱/     → 未分类的原始文件
知识库/     → 已分类 Markdown + docness-index.yml
工作台/     → 处理中的中间产物
发件箱/     → 最终输出
.logs/     → 操作日志（按日期）
```

## 前置条件与初始化

任何 SOP 开始前，先解析/初始化项目级工作区（从 docness 目录执行）：

```bash
python3 -m scripts.init_workspace "<项目根目录>"
```

流程：

1. **检查项目配置** — 在项目根目录查找 `AGENTS.md` / `agents.md` / `CLAUDE.md` / `claude.md`（存在多个时按此顺序取第一个），解析其中 `## Docness 工作目录` 章节的 YAML 配置（`docness:` 键）
2. **遵循声明** — 项目已声明工作区路径 → 按声明使用（相对路径基于 `root`，默认项目根目录），**不重建、不改写**
3. **缺失则初始化** — 未声明 → 在项目根目录创建 `知识库/` `收件箱/` `发件箱/` `工作台/`（含 `.logs/`），并把配置写回项目说明文件（无说明文件时新建 `AGENTS.md`）
4. **幂等** — 重复运行只补建缺失目录，不删除/覆盖已有内容；配置原地更新，不产生重复章节

写回配置示例：

```yaml
docness:
  root: .
  收件箱: 收件箱
  知识库: 知识库
  工作台: 工作台
  发件箱: 发件箱
  logs: .logs
```

- 各目录值为相对 `root` 的路径；`root` 相对项目根目录，默认 `.`；只声明部分目录时，未声明项回退默认名（如 `知识库`）
- 命令输出 JSON：`workspace`（各目录绝对路径）、`config_file`、`configured`。后续 SOP 一律使用这些**绝对路径**，严禁落到 skill 自身目录（如 `.claude/skills/docness/知识库/`）

## 脚本入口

标 🔧 的可 `python3 -m scripts.<name>` 命令行执行（有 main()），其余为供 agent import 的库函数。

| 脚本 | CLI | 功能 |
|------|-----|------|
| `scripts/init_workspace.py` | 🔧 | 工作区解析 + 幂等初始化（前置条件，见上） |
| `scripts/dispatch.py` | 🔧 | 输入识别 + 意图分发 |
| `scripts/complexity.py` | 🔧 | 复杂度指标提取 + 路由判定 |
| `scripts/classify.py` | 🔧 | 产出分类 prompt（agent 据此调 LLM） |
| `scripts/converter.py` | — | 转换编排器（simple/complex 路由 + 降级），由 collect SOP 调用 |
| `scripts/state.py` | — | front matter 读写 + 索引更新 |
| `scripts/index.py` | — | docness-index.yml 维护 |
| `scripts/utils.py` | — | 通用工具 |

## 错误处理

- 置信度低或不确定时，先问人，不自作决定
- 保留中间产物，记录错误到 `.logs/`
- 详见 `references/error-handling.md`

## 依赖 skill

> 以下 skill 为运行时委托对象，**需在目标环境单独安装**。docness 本体只做编排，不包含这些 skill。

| 来源 | skill | 用途 |
|------|-------|------|
| 外部（腾讯） | tencent-docs, tencent-meeting-mcp | 腾讯文档导出、腾讯会议纪要 |
| 外部（飞书 lark-cli） | lark-doc, lark-shared, lark-minutes, lark-vc | 飞书文档/妙记/会议 |
| 外部（baoyu-skills） | baoyu-url-to-markdown, baoyu-image-gen, baoyu-slide-deck | 网页抓取、配图、PPT |
| 外部（Anthropic） | docx, pdf, pptx | simple 管道全部失败后的兜底输出 |
| 本仓库 products/ | md2feishu | Markdown → 飞书文档 |
| skillshare 中央库 | transcribe, mineru | 音视频转写、复杂文档高保真转换 |

## 依赖系统工具

- **pandoc** (≥3.0): DOCX/PPTX/PDF 正反向转换的基石
- **LibreOffice** (可选): .doc/.ppt/.xls/.wps 旧格式桥接
- **Python 库**: pypdf, python-docx, python-pptx, pandas, openpyxl（复杂度指标提取 + 简单转换）
- **MinerU Skill**: 复杂文档高保真转换（通过官方 Skill 调用，无需本地安装）
