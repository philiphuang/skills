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

## URL 提炼（collect 完成后，原文.URL.md 三类分录）

> 来源：2026-08-30 三场景实践（6 个 md 提炼出 2 真实在线文档 + 内网 IP/外部工具站被过滤）。
> SOP 流程见 `sops/collect.md`「URL 提炼」。

- **范围**：读所有已入库 md（正文与附件），提取 `https?://` URL（排除 `mailto:`），去重。
- **过滤（仅 docness 可识别）**：只保留 docness 能拉取的来源——腾讯文档
  `docs.qq.com/sheet|doc|slide|docx`、飞书 `feishu.cn/docx|minutes|vc`、Lark `larksuite.com`、
  腾讯会议 `meeting.tencent.com`；**内网 IP、占位符、外部工具站（oschina/mirrors 等）不记录**。
- **落位**：`原文.URL.md` 与收件箱源文件**同名**（`{源文件名}.URL.md`），存收件箱目录下；
  知识库为入库副本。
- **三类分录**（三节分开）：① 提取到的 URL（仅 docness 可识别，附引用次数）；
  ② 拉取成功的；③ 拉取失败的（含原因）。不可混在一起。
- **拉取失败处理**：需登录的（腾讯文档/移动云盘等返回 HTML 登录页）→ 记录失败原因；
  已有本地导出 → 直接使用本地副本；无本地副本（如移动云盘）→ 向客户索要并记录待办。
- 附件提取阶段的 `外部URL.md` 是原始线索，`原文.URL.md` 是最终交付清单，两者不互相替代。

## 文档内嵌外部链接的甄别（附件提取链路）

从 OOXML 的 `*/_rels/*.rels` 提取外部链接时（`scripts/extract_attachments.py`）：

- 只有 `TargetMode="External"` 且 Type 为 hyperlink 的 Relationship 才是真外部 URL。
- **误标 mailto 排除规则**：`mailto:` 目标若不是合法邮箱地址（如 `mailto:详细信息列表如下中"认证账号"`，
  即把正文文字误设成了链接），必须排除，不计入外部 URL；合法邮箱地址保留。
- **`&amp;` 转义还原**：URL 中的 `&` 在 XML/rels 中被转义为 `&amp;`，落盘（如 `外部URL.md`）前需还原为 `&`
  （用 XML 解析器读取属性时自动还原，不要按字符串硬切）。
