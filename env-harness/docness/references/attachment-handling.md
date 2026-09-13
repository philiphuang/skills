# 附件与嵌入对象处理经验

> 来源：2026-08-27 真实任务《提取 .doc 文档中的附件与外部 URL》的踩坑沉淀
> （样本：WPS 生成的 36MB .doc，10 个 OLE 嵌入对象，去重后 8 个唯一附件 + 4 处外部链接）；
> 2026-08-30 三场景（预检预修 / 工单助理 / 录音质检）实践补充。
> 提取实现见 `scripts/extract_attachments.py`，SOP 流程见 `sops/collect.md`「附件与在线文档」。

## 旧格式解析

1. **`textutil` 处理不了 WPS 生成的 .doc**（报 `The file isn't in the correct format`）。
   macOS 上旧格式桥接优先走 LibreOffice headless；不可用再提示用户手动另存。
2. **LibreOffice 把 .doc 转 .docx 会丢失/合并大部分嵌入 OLE 对象**（实测 10 个对象转后仅剩 1 个）。
   提取嵌入附件**必须直接解析原始旧格式文件的 OLE `ObjectPool`**，不能依赖转换产物。
3. 旧格式嵌入对象在 OLE `ObjectPool/{id}/package` 流中，`package` 流本身就是
   **原始文件的完整字节**（通常以 `PK\x03\x04` zip 头开头），可原样保存为 .docx/.xlsx，无需二次解包。
4. 旧格式文件中的外部超链接存于二进制流，`extract_attachments.py` 不解析；
   如需提取旧格式的外部链接，先 LibreOffice 桥接为新格式再解析其 rels。

## 嵌入对象类型识别三板斧

1. **魔数**：`PK\x03\x04` → Office zip；`%PDF` → PDF；`D0 CF 11 E0` → 旧 OLE 复合文档；
2. **Office 类型特征路径**：`word/document.xml` → DOCX；`xl/workbook.xml` → XLSX；
   `ppt/presentation.xml` → PPTX；
3. **`docProps/core.xml` 的 `<dc:title>`**（可结合正文首段人工确认）用于确认"这是哪份文档"并据此命名。

新格式 .docx 中 `word/embeddings/oleObject*.bin` 本身还是 OLE 容器（`D0 CF 11 E0` 开头），
需要再读其中的 `package` 流才能拿到真实附件字节。

## 去重与命名

- **同一附件可能在正文中被引用多次**（实测 10 个对象中 2 对字节级相同）。按 md5 判重只保留一份，
  在清单中注明"文中引用 N 次"。
- 命名规则：**标题优先** `{标题}.{ext}`（标题取自 `docProps/core.xml` 的 `<dc:title>`）；
  无标题时退回 `附件{序号}.{ext}` 占位（见下「可识别命名铁律」，占位必须补名）。

## 可识别命名铁律（重要）

- **问题**：docx 的 `word/embeddings/` OLE Package 嵌入对象，**元数据不保留源文件名**
  （只有 `Microsoft_Word_Document1.docx` 之类 Word 占位名）。若剥离时用"嵌入附件N"占位命名，
  交付时无法识别身份。
- **要求**：剥离附件必须以**可识别命名**落位——从 `docProps/core.xml` 标题、
  或从文档内容**首行/标题**提炼文件名（如 `外呼样本导入文件格式说明.docx`），
  **禁止「附件N」/「嵌入附件N」占位交付**。无标题退回占位时，入库前必须提炼补名
  （`rename_attachment()`）。
- **验证**：OLE Package 的 `\x01Ole` 流与 package 内搜不到源文件名（仅占位），标题提炼是唯一途径。
- **同步（5 处）**：补名/重命名后，收件箱文件名 / 知识库 md / media 目录 / md 内引用 /
  索引 source / 主文档附件清单必须同步更新。

## 同文件去重（md5 落盘）

- **命名附件与 OLE 嵌入同文件**（md5 一致，工单助理场景实测：命名附件 附件1-8 与嵌入同文件）
  → **不重复剥离**，直接沿用命名附件，避免重复入库。
- 实现：写盘前与附件目录已有文件比对 md5（`_payload_digest`）——**与文件名无关**
  （目录内已有文件构建 digest 集合，循环前一次计算），一致即跳过。

## 提取范围：附件与图片分离（重要）

- **附件提取阶段只处理需进一步处理的附件**：docx/xlsx/pptx/pdf——这些才需递归走 collect 转换入库。
- **图片一律不落盘**（png/jpg/emf/wmf 等，`extract_attachments.py` 按魔数/类型识别后跳过）：
  media 由**转换阶段**（pandoc/MinerU）从源文档提取——避免同一图片双份处理、
  不增加源目录/附件目录清理工作量。跳过记入 notes（`跳过非处理附件 …`），不静默丢弃。

## 装饰性小文件丢弃

- **emf/wmf 旧格式矢量图**：pandoc 常同时产出 emf + png 副本（png 用于显示），emf 冗余 → 丢弃。
- **<5KB 小图标**（icon/logo 等）：装饰性，无信息价值 → 丢弃，不浪费存储与 token。
- 实现：`extract_attachments._is_decorative_image()` 按文件名 + 字节数判定——
  **当前无调用方**（附件提取阶段不落图片，天然不产生装饰文件），保留作下条规则的可执行说明，
  供后续转换脚本引用；转换阶段现由 agent 按本规则手工丢弃。

## 临时产物铁律

- 提取过程的中间产物（OLE 解包目录、LibreOffice 桥接 docx、`_正文提取.txt`、`attachments_raw/`、
  临时转换件）**一律放系统临时目录**（/tmp 或 `tempfile.TemporaryDirectory()`），**绝不落源文件目录**。
- 源文件目录只保留：**原文件 + 最终附件（命名件）**；中间产物用完即弃。
- 误例：工单助理同名子目录曾残留 `_提取输出/` 97M 临时产物，清理后目录才恢复干净结构。

## 知识库结构对称收件箱

- 转换产物的目录结构**必须与收件箱源文件结构对称**，附件移动后引用不断裂：
  - **主文档 md 与收件箱源文件平级**：`收件箱/客户提供/三场景/工单助理V0.9.0.doc` →
    `知识库/{category}/工单助理V0.9.0.md`。
  - **附件 md 进同名子目录**：`知识库/{category}/工单助理V0.9.0/附件A.md`，
    与收件箱 `<源文件去后缀>/` 子目录一一对应。
  - **media 按「每个 md 同名目录」分层**：`{md 名}.md` + `{md 名}/image1.png`。
- **附件移动后同步改 3 处**：① md 内 media 引用（`media/附件名/` → `../media/子目录/附件名/`）；
  ② 主文档附件清单相对链接（加子目录前缀）；③ 索引 `path` 字段。
- 实测代价：本次知识库结构重组修正 21 条索引 path、95+297 处 md 引用、22 处主文档清单链接；
  先定结构再入库，避免事后重构。

## 依赖

- `olefile`（`pip3 install olefile`，实测 0.47）：解析旧 .doc/.xls 及 oleObject 容器的必备库。

## 与正文路由的关系

附件提取是**并行的第二条产出线**：正文自身的转换继续走 docness 原有复杂度路由
（simple → pandoc/pandas；complex → MinerU），附件提取不影响正文路由。
提取出的附件再逐一递归走 collect 主流程入库。
