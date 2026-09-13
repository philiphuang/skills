# SOP: 处理 (Process)

职责：Markdown → 配图 / 转 Word / 转 PDF / 生成 PPT

## 前置条件：解析工作区

开始前先运行 `python3 -m scripts.init_workspace "<项目根目录>"` 解析项目级工作区（详见 SKILL.md「前置条件与初始化」）。
本文 `发件箱/`、`.logs/` 等一律指输出 JSON 中 `workspace` 的**绝对路径**，严禁落到 skill 自身目录。

## 触发方式

- `/docness process <文件路径> <处理类型>`
- 自然语言触发词见 `scripts/dispatch.py:PROCESS_TRIGGERS`

## 处理类型

转 Word/PDF/PPT 调用 `convert_from_markdown(md_path, target_format)`（由 pandoc 驱动，自动命名输出文件）；pandoc 失败时降级到对应 Anthropic Skill。配图走 `baoyu-image-gen`。

| 意图 | 实现 | 产物 |
|------|------|------|
| 转 Word | `convert_from_markdown(path, "docx")` → 降级 `docx` Skill | .docx |
| 转 PDF | `convert_from_markdown(path, "pdf")` → 降级 `pdf` Skill | .pdf |
| 生成 PPT | `convert_from_markdown(path, "pptx")`（简单文稿）→ `baoyu-slide-deck`（排版需求） | .pptx/.pdf |
| 配图 | `baoyu-image-gen` | 锚点 .md + img/ |

> PPT 有天花板：简单讲稿可行，精美排版需 baoyu-slide-deck。

## 配图流程

1. 复制源 Markdown 到 `发件箱/{name}.md`（锚点文件）
2. 创建 `发件箱/prompts/` 和 `发件箱/img/` 子目录
3. 从 Markdown 注释提取 prompt
4. 调用 `baoyu-image-gen` 生成图片
5. 在锚点 Markdown 中插入相对路径引用

## 记录

调用 `record_process(filepath, action, skill, outputs)` 写入 front matter。完成判据：front matter 的 `processing` 数组已追加本次记录（含 action/skill/outputs/processed_at）。
