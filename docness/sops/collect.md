# SOP: 收文件 (Collect)

职责：URL/本地文件 → 获取 → 复杂度判定 → 路由转换 → 分类保存

## 前置条件：解析工作区

开始前先解析项目级工作区（详见 SKILL.md「前置条件与初始化」），从 docness 目录执行：

```bash
WS=$(python3 -m scripts.init_workspace "<项目根目录>")
```

`WS` 是 JSON，`workspace` 内含 `收件箱` / `知识库` / `工作台` / `发件箱` / `logs` 的**绝对路径**。
本文所有 `收件箱/`、`知识库/`、`工作台/`、`发件箱/`、`.logs/` 一律指 WS 输出中的绝对路径，
**严禁落到 skill 自身目录**（如 `.claude/skills/docness/知识库/`）：

- 项目说明文件（`AGENTS.md` / `CLAUDE.md` 等）已声明工作区 → 遵循声明
- 未声明 → `init_workspace` 在项目根目录创建目录并把配置写回说明文件（幂等，重复运行不破坏已有目录）

## 流程

1. **输入识别** — 运行 `python3 -m scripts.dispatch "<输入>"`（从 docness 目录执行；输出仅用于识别意图，不产生文件），解析返回 JSON 获得 intent/subtype/source_type
2. **保存原始 URL** — URL 类型的输入先写入 `收件箱/{timestamp}-url.txt`（`收件箱` 取 WS 输出的绝对路径）
3. **本地文件** — 复制到 `收件箱/`（同上）
4. **格式转换** —— 两阶段路由：
   - **4a 旧格式桥接** — .doc/.ppt/.xls/.wps 先经 LibreOffice headless 转为新格式（.docx/.pptx/.xlsx）再进入判定。LibreOffice 不可用时提示用户手动另存，或降级走 Anthropic Skill。
   - **4b 复杂度判定路由** — 对新格式文件运行 `python3 -m scripts.complexity <文件路径> <文件类型>` 或调用 `decide_route()`：

     | 层级 | 判定逻辑 | 路由 |
     |------|---------|------|
     | **simple** | 低于复杂度阈值（普通文档） | 本地快速管道（pandoc / pypdf / pandas） |
     | **complex** | 超过复杂度阈值（页数/表格/图片超标） | MinerU Skill（高保真转换） |

     各格式简单管道：

     | 格式 | 工具 | 命令/库 |
     |------|------|--------|
     | Word (.docx) | **pandoc** | `pandoc input.docx -f docx -t gfm` |
     | PDF | **pandoc** → 降级 **pypdf** | pandoc 优先，失败回退 pypdf 提取 |
     | Excel (.xlsx) | **pandas + openpyxl** | `pd.read_excel()` + `df.to_markdown()` |
     | CSV | **pandas** | `pd.read_csv()` + `df.to_markdown()` |
     | PPT (.pptx) | **pandoc** | `pandoc input.pptx -f pptx -t gfm` |

     复杂管道：全部格式 → **MinerU Skill**（官方 opendatalab/MinerU-Ecosystem skills）。

     复杂度阈值见 `scripts/complexity.py:THRESHOLDS`（PDF/Word/Excel/PPT 各有页数/表格/图片等阈值），改阈值只改那一处。
   - **4c 特殊输入类型** — 腾讯文档/飞书/会议/网页/音视频不受复杂度路由影响，仍走原有 skill 链路（URL→来源类型映射见 `references/url-patterns.md`，权威定义在 `scripts/dispatch.py:URL_PATTERNS`）：
     - 腾讯文档 → `tencent-docs` → 导出下载 → 再按类型转换
     - 飞书文档 → `lark-doc`
     - **会议** → `tencent-meeting-mcp` / `lark-minutes` / `lark-vc`
       - 先获取会议主题（subject）和与会人列表（attendees）
       - 构建目录：`知识库/会议纪要/{yymmdd}{主题}/`（`知识库` 取 WS 输出的绝对路径）
       - 文件名：`generate_meeting_filename()` 返回 `(filename, directory)`
       - 示例：`260723-吴鸿涛黄志恒-企业平台沟通-纪要.md` → 目录 `260723企业平台沟通/`
     - 网页 → `baoyu-url-to-markdown`
     - 音视频 → `transcribe`

5. **分类** — 运行 `python3 -m scripts.classify <Markdown文件路径>`，拿到分类 prompt 后自行调用 LLM，再用 `parse_classify_response()` 解析返回 JSON 获得 category（见 `references/categories.md` 的分类规则）。
6. **入库** — 移动到 `知识库/{category}/`（`知识库` 取 WS 输出的绝对路径），生成规范文件名（这是必须完成的一步，不省略）
7. **记录** — 三项缺一不可，全部完成才算 collect 结束：
   - 调用 `record_collect(filepath, source, source_type, category, original_filename)` 写入 front matter（schema 见 `references/front-matter-schema.md`）
   - 调用 `index.add_entry(...)` 登记 `知识库/docness-index.yml`（`index_path` 传 WS 输出的 `知识库/docness-index.yml`）
   - 调用 `record_log(log_dir, action, detail)` 追加 `.logs/YYYY-MM-DD-docness.md` 条目（`log_dir` 取 WS 输出的 `logs`）

## 转换失败降级

```
simple 管道失败 → 自动升级为 complex（MinerU）
  ↓ MinerU 失败
Anthropic docx/pdf/pptx/xlsx Skill（兜底）
  ↓ 全部失败
报告用户，保留中间产物
```

## 用户交互

- 复杂度超标（路由到 MinerU）时不询问用户，静默执行
- 分类不确定时询问用户
- 处理完成后汇报结果（仅最终结果，不展开中间步骤）

