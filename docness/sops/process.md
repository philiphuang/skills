# SOP: 处理 (Process)

职责：Markdown → 配图 / 转 Word / 转 PDF / 生成 PPT

## 触发方式

- `/docness process <文件路径> <处理类型>`
- 自然语言触发词："配图"、"生成 PPT"、"转 PDF"、"转 Word"

## 处理类型

| 意图 | 调用 skill | 产物 |
|------|-----------|------|
| 配图 | `baoyu-image-gen` | 锚点 .md + img/ 目录 |
| 转 Word | `docx`（Anthropic，docx-js 生成） | .docx |
| 转 PDF | `pdf`（Anthropic，pypdf/reportlab 生成） | .pdf |
| 生成 PPT | `baoyu-slide-deck` | .pptx 或 .pdf |

## 配图流程

1. 复制源 Markdown 到 `发件箱/{name}.md`（锚点文件）
2. 创建 `发件箱/prompts/` 和 `发件箱/img/` 子目录
3. 从 Markdown 注释提取 prompt
4. 调用 `baoyu-image-gen` 生成图片
5. 在锚点 Markdown 中插入相对路径引用

## 记录

处理完成后更新 front matter processing 记录。
