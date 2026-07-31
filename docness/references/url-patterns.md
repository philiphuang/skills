# URL Pattern Recognition

> 权威定义在 `scripts/dispatch.py:URL_PATTERNS`，本表是人工可读披露。新增/修改 URL 模式改代码，再同步本表。

| Pattern | Source Type | Skill |
|---------|------------|-------|
| `docs.qq.com/sheet/*` | 腾讯表格 | `tencent-docs.manage.export_file` → `.xlsx` |
| `docs.qq.com/doc/*` | 腾讯文档 | `tencent-docs.manage.export_file` → `.docx` |
| `docs.qq.com/slide/*` | 腾讯幻灯片 | `tencent-docs.manage.export_file` → `.pptx` |
| `docs.qq.com/docx/*` | 腾讯智能文档 | `tencent-docs.get_content` |
| `docs.qq.com/*` | 腾讯文档（其他） | `tencent-docs.get_content` |
| `*.feishu.cn/docx/*` | 飞书文档 | `lark-doc` |
| `*.feishu.cn/minutes/*` | 飞书妙记 | `lark-minutes` |
| `*.feishu.cn/vc/*` | 飞书会议 | `lark-vc` |
| `*.larksuite.com/*` | Lark 文档 | `lark-doc` |
| `meeting.tencent.com/*` | 腾讯会议 | `tencent-meeting-mcp` |
| `*.md` (URL or local) | Markdown | send intent (if no other intent) |
| Other URL | 通用网页 | `baoyu-url-to-markdown` |
| Local `.docx`/`.doc` | Word 文件 | pandoc（优先）→ MinerU（复杂）→ Anthropic `docx`（兜底） |
| Local `.xlsx` | Excel 文件 | pandas+openpyxl → MinerU（复杂） |
| Local `.pptx`/`.ppt` | PPT 文件 | pandoc（优先）→ MinerU（复杂）→ Anthropic `pptx`（兜底） |
| Local `.pdf` | PDF 文件 | pandoc/pypdf（优先）→ MinerU（复杂）→ Anthropic `pdf`（兜底） |
| Local `.md` | Markdown | send intent |
| Local `.csv`/`.txt` | 纯文本 | pandas（CSV）/ 直接分类 |
| Local `.mp3`/`.mp4`/`.wav` | 音视频 | `transcribe` |

## 复杂度路由

| 复杂度 | 判定 | 工具 |
|-------|------|------|
| simple | 低于阈值（普通文档） | pandoc / pypdf / pandas |
| complex | 超过阈值（页数/表格/图片超标） | MinerU Skill |

阈值见 `scripts/complexity.py:THRESHOLDS`。
