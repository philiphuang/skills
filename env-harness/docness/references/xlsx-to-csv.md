# xlsx 转 csv 规则

> 来源：2026-08-30 真实任务《工单助理-智能体功能及请求的接口.xlsx（8 sheet）》的踩坑沉淀。
> 实现见 `scripts/converter.py`（`excel_to_csvs()` / `_xlsx_xml_parse()`），SOP 流程见 `sops/collect.md`「xlsx 转 csv 规则」。

## 为什么 xlsx 不转 md

- xlsx 是**多 sheet 表格**，md 表格无法保留 sheet 结构；拍平后数据不可读（8 sheet 混在一个 md 里）。
- **改为转 csv**：构建与 excel 同名的子目录，**一 sheet 一 csv**，csv 以 sheet 名为文件名。
  数据可读性最好，Excel/WPS 可直接打开。
- 入库：每个 csv 走 collect 三件套（front matter + index + log），索引 path 指向 csv 文件；
  主文档附件清单链接同步改 csv。不产出 md，索引中不留 md 条目。

## 编码：utf-8-sig

csv 一律写 **`utf-8-sig`**（带 BOM）：

- Excel/WPS 双击打开带 BOM 的 csv 不乱码（无 BOM 的 utf-8 csv 会被按本地编码猜，中文乱码）。
- 实现：Python `open(..., encoding="utf-8-sig")` 写入即自动带 BOM。

## 异常 xlsx：openpyxl 崩溃（`Fill() takes no arguments`）

- 部分 xlsx 的 `styles.xml` 与 openpyxl 版本不兼容，`load_workbook` / `ExcelFile` 直接抛
  `Fill() takes no arguments` 崩溃；**read_only 模式同样失败**（同一解析路径）。
- **绕开方案（已验证）**：zipfile XML 直解，不经过 openpyxl：

  | 部件 | 作用 |
  |------|------|
  | `xl/workbook.xml` | sheet 名（`<sheet name="...">`） |
  | `xl/_rels/workbook.xml.rels` | `r:id` → 实际 sheetN.xml 路径（Target） |
  | `xl/sharedStrings.xml` | 共享字符串表（`<si><t>` 拼合） |
  | `xl/worksheets/sheetN.xml` | 单元格：`<c t="s">`（索引共享字符串）、`t="inlineStr"`（内联文本）、其余读 `<v>` 原值 |

- **列号**：`<c r="B3">` 的 `r` 属性是 Excel 列号，需 A/AA/… 转数字列（实现 `_excel_col()`）。
- **空 sheet**：无 `<row>` 的 sheet 也落一个空 csv，保持"一 sheet 一 csv"完整。
- 取值规整：数值 `30.0` → `30`；`None`/空单元格 → 空串；多行/逗号交给 `csv` 模块引用处理。

## 常见坑

1. **sheet 名含非法字符**（`/` `\` 等）不能直接当文件名 → 清洗为 `_`。
2. **不要用 `df.to_markdown()` 拍平多 sheet**——结构丢失且 md 表格里嵌换行会碎。
3. 转换失败的 xlsx 走 simple 管道自动升级 complex（MinerU）的降级链；
   XML 直解仍失败时**保留中间产物、报告用户**（见 `sops/collect.md`「转换失败降级」）。
