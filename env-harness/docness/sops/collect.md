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

## 临时产物铁律（先读）

> **中间产物一律放系统临时目录（/tmp 或 `tempfile.TemporaryDirectory()`），绝不落源文件目录。**

中间产物包括：OLE 解包目录、LibreOffice 桥接 docx、`_正文提取.txt`、`attachments_raw/`、临时转换件。
源文件目录只保留：**原文件 + 最终附件（命名件）**。中间产物用完即弃；
若误落源目录，处理后必须清理（误例：工单助理同名子目录曾残留 `_提取输出/` 97M 临时产物）。
经验细节见 `references/attachment-handling.md`「临时产物铁律」。

## 流程

1. **输入识别** — 运行 `python3 -m scripts.dispatch "<输入>"`（从 docness 目录执行；输出仅用于识别意图，不产生文件），解析返回 JSON 获得 intent/subtype/source_type
2. **保存原始 URL** — URL 类型的输入先写入 `收件箱/{timestamp}-url.txt`（`收件箱` 取 WS 输出的绝对路径）
3. **本地文件** — 复制到 `收件箱/`（同上）
4. **格式转换** —— 两阶段路由：
   - **4a 旧格式桥接** — .doc/.ppt/.xls/.wps 先经 LibreOffice headless 转为新格式（.docx/.pptx/.xlsx）再进入判定。LibreOffice 不可用时提示用户手动另存，或降级走 Anthropic Skill。桥接产物放系统临时目录。
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
     | Excel (.xlsx) | **pandas + openpyxl** | **转 csv**（见下「xlsx 转 csv 规则」），**不转 md** |
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
   - **4d 附件与在线文档提取** — 正文转换（4a/4b）之外并行的第二条产出线，详见下文「附件与在线文档」：
     检测嵌入附件/外部链接 → 存 `工作台/{正文名去后缀}/` → 逐一按本 SOP 递归处理入库。附件提取不影响正文路由。

### xlsx 转 csv 规则

> xlsx 是多 sheet 表格，md 无法保留 sheet 结构；**不转 md**，一 sheet 一 csv 可读性最好。

1. **落位**：构建与 excel **同名的子目录**（`{excel 名}/{sheet 名}.csv`），一 sheet 一 csv，**csv 以 sheet 名为文件名**。
   异常 sheet 名（含 `/` `\` 等非法字符）先清洗为 `_`。
2. **编码**：csv 一律写 **`utf-8-sig`**（带 BOM，Excel/WPS 双击打开不乱码）。
3. **转换实现**：优先 `pandas + openpyxl`（`scripts/converter.py:excel_to_csvs()`）；openpyxl 打不开的异常 xlsx
   （`styles.xml` 不兼容导致 `Fill() takes no arguments` 崩溃，read_only 模式同样失败）**回退 zipfile XML 直解**：
   `xl/workbook.xml` 读 sheet 名（经 `xl/_rels/workbook.xml.rels` 的 r:id 映射到 sheetN.xml）、
   `xl/sharedStrings.xml` 读共享字符串、`xl/worksheets/sheetN.xml` 按 `<c>` 单元格的
   `t="s"`（共享字符串索引）/`t="inlineStr"`（内联文本）/其余（原值）取值拼表。
   经验细节见 `references/xlsx-to-csv.md`。
4. **入库**：每个 csv 走 collect 三件套（front matter + index + log），索引 path 指向 csv 文件；
   主文档附件清单链接同步改 csv。**不产出 md，索引中也不留 md 条目。**

## 附件与在线文档

适用时机：正文文件（.doc/.docx/.ppt/.pptx/.xls/.xlsx/.wps）可能内嵌附件对象或包含指向在线文档的外部链接。
正文按 4a–4c 转换之外，并行执行本节流程。

1. **检测与提取** — 对**原始文件**运行（`工作台` 取 WS 输出的绝对路径）：

   ```bash
   python3 -m scripts.extract_attachments "<原始文件>" --outdir "<工作台/{正文名去后缀}>"
   ```

   - 旧格式（.doc/.ppt/.xls/.wps）：`olefile` 直接解析 OLE `ObjectPool/{id}/package` 流。
     **不能用 LibreOffice 桥接产物检测**——桥接会丢失大部分嵌入对象（实测 10 个只剩 1 个）
   - 新格式（.docx/.pptx/.xlsx）：解包扫描 `*/embeddings/`，并解析 `*/_rels/*.rels` 中
     `TargetMode="External"` 的 hyperlink 得到外部链接
   - 返回 JSON：附件逐一原样写盘到附件目录（魔数 + Office 特征路径 + `docProps/core.xml` 标题识别类型并命名，
     md5 去重、记录引用次数）；外部链接写入附件目录下 `外部URL.md`（误标 mailto 已排除、`&amp;` 已还原）。
     经验细节见 `references/attachment-handling.md`
2. **提取范围（只处理附件 + URL）**：
   - **只落「需进一步处理的附件」**：docx/xlsx/pptx/pdf——这些才需递归走 collect 转换入库。
   - **图片一律不落盘**（png/jpg/emf 等）：由转换阶段（pandoc/MinerU）从源文档提取 media，
     见下「media 规则」——避免同一图片双份处理、不增加后续清理工作量。
     非附件字节流记入 notes（`跳过非处理附件 …`），不静默丢弃。
   - **附件命名与去重（铁律）**：
     - **可识别命名落位**：从 `docProps/core.xml` 标题、或从文档内容首行/标题提炼真实文件名
       （如 `外呼样本导入文件格式说明.docx`），**禁止「附件N」/「嵌入附件N」占位交付**。
       脚本以标题优先命名（`extract_attachments.py`），无标题退回 `附件N` 占位时，
       须在入库前提炼补名（可用 `rename_attachment()`），并同步 5 处：
       收件箱文件名 / 知识库 md / media 目录 / md 内引用 / 索引 source / 主文档附件清单。
       原因：docx `word/embeddings/` 的 OLE Package 元数据不保留源文件名（只有
       `Microsoft_Word_Document1.docx` 之类 Word 占位名），**标题提炼是唯一途径**。
     - **md5 落盘去重**：命名附件与 OLE 嵌入同文件时（md5 一致，**与文件名无关**）
       **不重复剥离**；与附件目录已有文件 md5 一致也跳过。全流程按 md5 去重，避免重复入库。
3. **在线文档下载** — 读 `外部URL.md`，按 `references/url-patterns.md` 的来源映射**逐一下载到同一附件目录**：
   腾讯文档 → `tencent-docs` 导出；飞书 → `lark-doc`；网页 → `baoyu-url-to-markdown`；
   需要登录/无法下载的链接记录到 `.logs/` 并在最终汇报中列出，不静默跳过
4. **递归处理** — 对附件目录里的每个文件**复用本 SOP 主流程**（步骤 4 起）：
   复杂度判定 → simple/complex 路由 → md/csv → 分类 → 入 `知识库/{category}/` →
   记录 front matter + index + log（与正文同规；`source` 注明来源正文文件名）
5. **递归控制** — 附件里再嵌附件时同上递归，但最多 2 层；全程按 md5 去重，
   已处理过的附件不重复入库，避免死循环

任一附件处理失败不影响其余附件与正文：记录错误到 `.logs/`，继续下一个。

### 知识库结构对称收件箱（铁律）

> 转换产物的目录结构**必须与收件箱源文件结构对称**，附件移动后引用不断裂。

- **主文档 md 与收件箱源文件平级**：`收件箱/客户提供/三场景/工单助理V0.9.0.doc` →
  `知识库/{category}/工单助理V0.9.0.md`（不额外套目录）。
- **附件 md 进同名子目录**：附件 md 与源附件落在 `<主文档名>/` 同名子目录里——
  `知识库/{category}/工单助理V0.9.0/附件A.md`，与收件箱 `<源文件去后缀>/` 子目录一一对应。
- **media 按「每个 md 同名目录」分层**：`{md 名}.md` + `{md 名}/image1.png`（见下「media 规则」）。
- **附件移动后同步改 3 处**（附件 md 从平铺改为同名子目录等结构调整时）：
  ① md 内 media 引用（`media/附件名/` → `../media/子目录/附件名/`，按新相对位置重算）；
  ② 主文档附件清单**相对链接**（加子目录前缀）；③ 索引 `path` 字段。
  改完逐项核对，保证全链路零断裂。

### media 规则

- **media 是转换产物的图片库**，不是源文档自带附件——docx 内嵌图片（`word/media/`）经 pandoc 提取后独立成文件，
  md 才能 `<img src>` 引用。**图片只在转换阶段从源文档提取**：附件提取阶段（`extract_attachments`）
  不落任何图片（见「附件与在线文档」提取范围）。
- **不落独立 `media/` 目录**，而是**每个 md 同名目录**：`知识库/{category}/{主文档名}.md` + `{主文档名}/image1.png`；
  附件同理 `子目录/{附件名}.md` + `{附件名}/imageN.png`。
- **装饰性小文件丢弃**：emf 旧格式矢量图（有 png 副本时冗余）、<5KB 小图标，转换时即丢弃。
- **引用路径同步**：media 重构后，md 内 `media/主文档名/` → `主文档名/`，
  附件 `../media/子目录/附件名/` → `附件名/`。

## URL 提炼（原文.URL.md）

> collect 完成后（正文 + 全部附件入库后），对所有已入知识库的 md 统一提炼在线文档 URL。

1. **提炼范围**：读**所有 md**（正文与附件），提取 `https?://` URL（排除 `mailto:`），**去重**。
2. **过滤（仅 docness 可识别）**：只保留 docness 能拉取的来源——
   腾讯文档 `docs.qq.com/sheet|doc|slide|docx`、飞书 `feishu.cn/docx|minutes|vc`、
   Lark `larksuite.com`、腾讯会议 `meeting.tencent.com`。
   **内网 IP、占位符、外部工具站（oschina/mirrors 等）不记录。**
3. **落位与命名**：生成 `原文.URL.md`——**与收件箱源文件同名**（源文件 `家集客...工单助理V0.9.0.doc`
   → `家集客...工单助理V0.9.0.URL.md`），**存收件箱** `收件箱/{原文目录}/`；知识库为入库副本
   （与源文件 md 同目录）。
4. **三类分录**（三节分开记录，不可混在一起）：
   ① **提取到的 URL**（仅 docness 可识别，附文中引用次数）；
   ② **拉取成功的**；③ **拉取失败的**（**含原因**）。
5. **拉取失败的处理**：
   - **需登录的**（腾讯文档/移动云盘等，返回 HTML 登录页而非真实内容）→ 记录失败原因；
     已有**本地导出**的（如腾讯文档 xlsx）**直接使用本地副本**；
     无本地副本的（如移动云盘）→ **向客户索要**，并记录待办。
   - 失败链接同时记录到 `.logs/` 并在最终汇报中列出，不静默跳过。
6. 附件提取阶段的 `外部URL.md` 是原始线索；`原文.URL.md` 是最终交付清单，两者不互相替代。

## 主文档闭环核对清单（5 项）

主文档 collect 完成后，**逐项核对**（主文档 md 存在 ≠ 闭环完成，工单助理场景实测踩坑）：

- [ ] ① **front matter source 为当前实际路径**（源文件可能被移动，source 会过期失效）
- [ ] ② **末尾有附件清单章节**（嵌入附件/URL 清单的入库位置与引用点，见 `references/attachment-handling.md`）
- [ ] ③ **索引有主文档条目**（collect 时可能漏登主文档，只登了附件）
- [ ] ④ **附件 md 与索引 source 指向权威附件目录**（同名子目录，而非旧临时目录/平铺路径）
- [ ] ⑤ **临时产物已清理**（`_提取输出/`、LibreOffice 桥接 docx、解包目录等，见「临时产物铁律」）

任一核对不过 → 修正后再算闭环完成。

## 分类与入库

1. **分类** — 运行 `python3 -m scripts.classify <Markdown文件路径>`，拿到分类 prompt 后自行调用 LLM，再用 `parse_classify_response()` 解析返回 JSON 获得 category（见 `references/categories.md` 的分类规则）。
2. **入库** — 移动到 `知识库/{category}/`（`知识库` 取 WS 输出的绝对路径），生成规范文件名（这是必须完成的一步，不省略）；
   media 图片随 md 进入同名子目录。
3. **记录** — 三项缺一不可，全部完成才算 collect 结束：
   - 调用 `record_collect(filepath, source, source_type, category, original_filename)` 写入 front matter（schema 见 `references/front-matter-schema.md`）
   - 调用 `index.add_entry(...)` 登记 `知识库/docness-index.yml`（`index_path` 传 WS 输出的 `知识库/docness-index.yml`）
   - 调用 `record_log(log_dir, action, detail)` 追加 `.logs/YYYY-MM-DD-docness.md` 条目（`log_dir` 取 WS 输出的 `logs`）
4. **URL 提炼 + 闭环核对** — 全部入库后执行「URL 提炼」与「主文档闭环核对清单」。

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
