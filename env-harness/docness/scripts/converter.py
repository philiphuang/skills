"""文档转换编排器——根据复杂度判定结果，路由到对应转换工具链。

工具链总图：
  simple: pandoc (DOCX/PPTX/PDF) / pypdf (PDF) / excel_to_csvs (Excel → 同名子目录 + 每 sheet 一个 csv)
  complex: MinerU Skill → 高精度 Markdown
  旧格式 (.doc/.ppt/.xls/.wps): LibreOffice headless → 新格式 → 继续

反向:
  pandoc: Markdown → PDF/DOCX/PPTX
  pandas: CSV/DataFrame → XLSX

xlsx 不转 md：多 sheet 结构 md 无法保留，改为同名子目录 + 一 sheet 一 csv（utf-8-sig）；
openpyxl 打不开的异常 xlsx（如 styles.xml 不兼容导致 Fill() takes no arguments 崩溃）
回退 zipfile XML 直解（xl/workbook.xml sheet 名 + xl/sharedStrings.xml + xl/worksheets/sheetN.xml）。
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from xml.etree import ElementTree

from .complexity import decide_route


def convert_to_markdown(
    filepath: str | Path,
    file_type: str | None = None,
    force_route: str | None = None,
) -> dict:
    """将文档文件转换为 Markdown。

    决策流程：
    1. file_type → 提取复杂度指标
    2. 判定 simple/complex
    3. 路由到对应转换工具
    4. 返回转换结果

    Args:
        filepath: 输入文件路径
        file_type: 文件类型标识，None 时自动检测
        force_route: 强制路由 "simple" | "complex"，None 时自动判定

    Returns:
        {
            "success": bool,
            "output_path": str | None,
            "content": str | None,
            "route": "simple" | "complex",
            "tool": str,
            "error": str | None,
        }
    """
    from scripts.utils import detect_file_type

    path = Path(filepath)

    if file_type is None:
        file_type = detect_file_type(str(path))

    # 旧格式需先转新格式
    legacy_types = {
        "word-legacy": "word",
        "powerpoint-legacy": "powerpoint",
        "excel-legacy": "excel",
    }
    if file_type in legacy_types:
        return _convert_legacy_via_libreoffice(path, file_type)

    # 复杂度判定
    if force_route:
        route = force_route
        decision = {"route": route, "recommended_tool": ""}
    else:
        decision = decide_route(str(path), file_type)
        route = decision["route"]

    # 路由分发
    if route == "complex":
        return _route_to_mineru(path, file_type, decision)
    else:
        result = _route_simple(path, file_type, decision)
        # 降级链：simple 管道尝试过但失败 → 自动升级 complex（MinerU）。
        # 注意：仅当存在对应转换器却失败时才升级；不支持的文件类型（tool=="none"）
        # MinerU 同样无法处理，直接返回错误。
        if not result.get("success") and result.get("tool") != "none":
            fallback = _route_to_mineru(
                path, file_type, {"reasons": [f"simple 管道失败({result.get('tool')})"]}
            )
            fallback["fallback_from"] = "simple"
            return fallback
        return result


def _convert_legacy_via_libreoffice(path: Path, file_type: str) -> dict:
    """旧格式(.doc/.ppt/.xls/.wps) 通过 LibreOffice headless 转为现代格式。

    如果 LibreOffice 不可用，降级使用 Anthropic Skill。
    """
    import shutil
    import subprocess
    import tempfile

    lo_path = shutil.which("libreoffice") or shutil.which("soffice")

    if lo_path is None:
        return {
            "success": False,
            "output_path": None,
            "content": None,
            "route": "legacy",
            "tool": "none",
            "error": "LibreOffice 不可用，请安装 LibreOffice 或将文件手动另存为新格式（.docx/.pptx/.xlsx）",
        }

    # 映射旧格式到目标新格式
    target_format: dict[str, str] = {
        "word-legacy": "docx",
        "powerpoint-legacy": "pptx",
        "excel-legacy": "xlsx",
    }

    ext = target_format.get(file_type, "docx")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        cmd = [
            lo_path,
            "--headless",
            "--convert-to",
            ext,
            "--outdir",
            str(tmpdir_path),
            str(path),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            return {
                "success": False,
                "output_path": None,
                "content": None,
                "route": "legacy",
                "tool": "libreoffice",
                "error": f"LibreOffice 转换失败: {result.stderr}",
            }

        # 找到转换后的文件
        converted_files = list(tmpdir_path.glob(f"*.{ext}"))
        if not converted_files:
            return {
                "success": False,
                "output_path": None,
                "content": None,
                "route": "legacy",
                "tool": "libreoffice",
                "error": "LibreOffice 转换后未找到输出文件",
            }

        new_path = converted_files[0]
        ext_to_type = {"docx": "word", "pptx": "powerpoint", "xlsx": "excel"}
        new_type = ext_to_type.get(ext, "word")

        # 递归转换（对已转换的新格式再做复杂度判定）
        return convert_to_markdown(str(new_path), file_type=new_type)


def _route_simple(path: Path, file_type: str, decision: dict) -> dict:
    """简单文档走本地快速管道。"""
    converters = {
        "word": _simple_word,
        "excel": _simple_excel,
        "csv": _simple_csv,
        "pdf": _simple_pdf,
        "powerpoint": _simple_powerpoint,
    }

    converter = converters.get(file_type)
    if converter is None:
        return {
            "success": False,
            "output_path": None,
            "content": None,
            "route": "simple",
            "tool": "none",
            "error": f"不支持的文件类型: {file_type}",
        }

    return converter(path)


def _simple_word(path: Path) -> dict:
    """pandoc 转换 DOCX → Markdown。"""
    import subprocess

    result = subprocess.run(
        ["pandoc", str(path), "-f", "docx", "-t", "gfm", "--wrap=none"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        return {
            "success": False,
            "output_path": None,
            "content": None,
            "route": "simple",
            "tool": "pandoc",
            "error": f"pandoc 转换失败: {result.stderr}",
        }

    output_path = path.with_suffix(".md")
    output_path.write_text(result.stdout, encoding="utf-8")

    return {
        "success": True,
        "output_path": str(output_path),
        "content": result.stdout,
        "route": "simple",
        "tool": "pandoc",
        "error": None,
    }


def _simple_pdf(path: Path) -> dict:
    """pypdf 提取 PDF 文本内容。"""
    import subprocess

    # 优先尝试 pandoc（支持更复杂的 PDF 结构）
    result = subprocess.run(
        [
            "pandoc", str(path), "-f", "pdf",
            "-t", "gfm", "--wrap=none",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    tool = "pandoc"
    content = ""
    error = None

    if result.returncode != 0:
        # pandoc 失败，降级到 pypdf
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
            content = "\n\n".join(parts)
            tool = "pypdf"
        except Exception as e:
            return {
                "success": False,
                "output_path": None,
                "content": None,
                "route": "simple",
                "tool": "pypdf",
                "error": f"PDF 文本提取失败: {e}",
            }
    else:
        content = result.stdout

    output_path = path.with_suffix(".md")
    output_path.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "output_path": str(output_path),
        "content": content,
        "route": "simple",
        "tool": tool,
        "error": error,
    }


def excel_to_csvs(path: Path) -> dict:
    """Excel → 同名子目录 + 每 sheet 一个 csv（utf-8-sig）。

    构建与 excel 同名的子目录，csv 以 sheet 名为文件名；不转 md。
    优先 pandas+openpyxl；openpyxl 打不开的异常 xlsx（styles.xml 不兼容导致
    `Fill() takes no arguments` 崩溃，read_only 模式同样失败）回退 zipfile XML 直解
    （xl/workbook.xml 读 sheet 名 + xl/sharedStrings.xml 读共享字符串 +
    xl/worksheets/sheetN.xml 读单元格），见 _xlsx_xml_parse。

    Returns:
        {
            "success": bool,
            "output_dir": str | None,   # 同名子目录（csv 所在）
            "outputs": list[str] | None,  # 每 sheet 一个 csv 的路径
            "tool": str,                # "pandas+openpyxl" | "zipfile-xml"
            "error": str | None,
        }
    """
    try:
        import pandas as pd

        xlsx = pd.ExcelFile(str(path), engine="openpyxl")
        sheets = xlsx.sheet_names
        tables: list[tuple[str, list[list[str]]]] = []
        for sheet_name in sheets:
            df = pd.read_excel(xlsx, sheet_name=sheet_name)
            df = df.dropna(how="all").astype(object).where(df.notna(), None)
            rows = [[_csv_cell(v) for v in row] for row in df.values.tolist()]
            if rows:
                rows = [list(df.columns)] + rows
            tables.append((sheet_name, rows))
        tool = "pandas+openpyxl"
    except Exception:
        # openpyxl 不兼容的异常 xlsx → zipfile XML 直解
        try:
            tables = _xlsx_xml_parse(path)
        except Exception as e:
            return {
                "success": False,
                "output_dir": None,
                "outputs": None,
                "tool": "zipfile-xml",
                "error": f"无法读取 Excel 文件（openpyxl 与 XML 直解均失败）: {e}",
            }
        tool = "zipfile-xml"

    out_dir = path.parent / path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[str] = []
    for sheet_name, rows in tables:
        # sheet 名含非法字符（/ \ : 等）不能直接当文件名 → 清洗为 _
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", sheet_name).strip()
        if not safe_name:
            safe_name = "sheet"
        sheet_file = out_dir / f"{safe_name}.csv"
        # utf-8-sig 带 BOM：空文件时 open(encoding="utf-8-sig") 不写 BOM，先显式写 BOM；
        # TextIOWrapper 的缓冲需在文件关闭前 flush（否则数据停留在缓冲区不落盘）
        with sheet_file.open("wb") as f:
            f.write(b"\xef\xbb\xbf")
            wrapper = io.TextIOWrapper(f, encoding="utf-8", newline="")
            writer = csv.writer(wrapper)
            for row in rows:
                writer.writerow(row)
            wrapper.flush()
        outputs.append(str(sheet_file))

    return {
        "success": True,
        "output_dir": str(out_dir),
        "outputs": outputs,
        "tool": tool,
        "error": None,
    }


def _csv_cell(value) -> str:
    """把单元格值规整为 CSV 字符串（多行/逗号交给 csv 模块引用处理）。"""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _xlsx_xml_parse(path: Path) -> list[tuple[str, list[list[str]]]]:
    """zipfile 直解 xlsx：不依赖 openpyxl 的兼容性。

    读 xl/workbook.xml 的 sheet 名（按 r:id → xl/_rels/workbook.xml.rels 的
    Target 得 sheetN.xml 路径）、xl/sharedStrings.xml 的共享字符串、
    xl/worksheets/sheetN.xml 的 <c> 单元格（t="s" 索引共享字符串，
    t="inlineStr" 读内联文本，其余取原始值），按行列拼表。
    """
    import zipfile

    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if "xl/workbook.xml" not in names:
            raise ValueError("不是有效的 xlsx（缺少 xl/workbook.xml）")

        sheet_names = _xlsx_sheet_names(zf)
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.iter():
                if si.tag.endswith("}si"):
                    shared.append("".join(t.text or "" for t in si.iter() if t.tag.endswith("}t")))

        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        tables: list[tuple[str, list[list[str]]]] = []
        for sheet_name, sheet_path in sheet_names:
            if sheet_path not in names:
                continue
            root = ElementTree.fromstring(zf.read(sheet_path))
            rows: list[list[str]] = []
            for row in root.iter(f"{ns}row"):
                cells: dict[int, str] = {}
                col = 0
                for c in row.iter(f"{ns}c"):
                    ref = c.get("r", "")
                    col = _excel_col(ref) if ref else col + 1
                    val = _xlsx_cell_value(c, shared)
                    if val != "":
                        cells[col] = val
                if not cells:
                    continue
                width = max(cells)
                rows.append([cells.get(i, "") for i in range(1, width + 1)])
            tables.append((sheet_name, rows))

        # 空 sheet（无数据行）也保留：落一个仅表头行空 csv
        for sheet_name, _ in sheet_names:
            if not any(s == sheet_name for s, _ in tables):
                tables.append((sheet_name, []))

    return tables


def _xlsx_sheet_names(zf) -> list[tuple[str, str]]:
    """读 workbook.xml + workbook.xml.rels 得到 (sheet 名, sheetN.xml 路径)。"""
    wb_root = ElementTree.fromstring(zf.read("xl/workbook.xml"))
    rels: dict[str, str] = {}
    try:
        rels_root = ElementTree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in rels_root:
            if rel.tag.endswith("}Relationship"):
                rels[rel.get("Id", "")] = rel.get("Target", "")
    except KeyError:
        pass

    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    sheets: list[tuple[str, str]] = []
    for sheet in wb_root.iter(f"{ns}sheet"):
        name = sheet.get("name", "")
        rid = sheet.get(f"{rel_ns}id", "")
        target = rels.get(rid, "")
        if not target.startswith("xl/"):
            target = f"xl/{target.lstrip('/')}"
        sheets.append((name, target))
    return sheets


def _xlsx_cell_value(c, shared: list[str]) -> str:
    """按 <c> 的 t 属性取单元格文本：s→共享字符串、inlineStr→内联文本、其余原值。"""
    t = c.get("t", "")
    if t == "s":
        try:
            v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
            idx = int(v.text or "0")
            return shared[idx] if idx < len(shared) else ""
        except (ValueError, AttributeError, IndexError):
            return ""
    if t == "inlineStr":
        text = "".join(
            t.text or ""
            for t in c.iter()
            if t.tag.endswith("}t")
        )
        return text
    v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
    return v.text if v is not None and v.text else ""


def _excel_col(ref: str) -> int:
    """把 Excel 列号（A/B/.../AA/...）转 1 基数字列；ref 形如 "B3"。"""
    col_part = re.match(r"[A-Za-z]+", ref)
    if not col_part:
        return 1
    n = 0
    for ch in col_part.group().upper():
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def _simple_excel(path: Path) -> dict:
    """xlsx 不转 md：构建同名子目录，一 sheet 一 csv（utf-8-sig）。"""
    return excel_to_csvs(path)


def _simple_csv(path: Path) -> dict:
    """pandas 转换 CSV → Markdown 表格。"""
    try:
        import pandas as pd
    except ImportError:
        return {
            "success": False,
            "output_path": None,
            "content": None,
            "route": "simple",
            "tool": "pandas",
            "error": "pandas 未安装",
        }

    try:
        df = pd.read_csv(str(path))
    except Exception as e:
        return {
            "success": False,
            "output_path": None,
            "content": None,
            "route": "simple",
            "tool": "pandas",
            "error": f"无法读取 CSV 文件: {e}",
        }

    content = f"# {path.stem}\n\n{df.to_markdown(index=False)}\n"
    output_path = path.with_suffix(".md")
    output_path.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "output_path": str(output_path),
        "content": content,
        "route": "simple",
        "tool": "pandas",
        "error": None,
    }


def _simple_powerpoint(path: Path) -> dict:
    """pandoc 转换 PPTX → Markdown。"""
    import subprocess

    result = subprocess.run(
        ["pandoc", str(path), "-f", "pptx", "-t", "gfm", "--wrap=none"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        return {
            "success": False,
            "output_path": None,
            "content": None,
            "route": "simple",
            "tool": "pandoc",
            "error": f"pandoc PPTX 转换失败: {result.stderr}",
        }

    output_path = path.with_suffix(".md")
    output_path.write_text(result.stdout, encoding="utf-8")

    return {
        "success": True,
        "output_path": str(output_path),
        "content": result.stdout,
        "route": "simple",
        "tool": "pandoc",
        "error": None,
    }


def _route_to_mineru(path: Path, file_type: str, decision: dict) -> dict:
    """复杂文档路由到 MinerU Skill。

    注意：MinerU 通过 Skill 调用（非本地安装），此处返回路由指令
    供上层 Agent 解释执行。
    """
    return {
        "success": None,  # 需 Agent 执行
        "output_path": None,
        "content": None,
        "route": "complex",
        "tool": "MinerU",
        "error": None,
        "instruction": (
            f"文件 {path.name} 超出简单阈值（{', '.join(decision.get('reasons', []))}），"
            f"请调用 MinerU Skill 进行高保真转换。"
        ),
        "decision": decision,
    }


def convert_from_markdown(
    md_path: str | Path,
    target_format: str,
) -> dict:
    """从 Markdown 反向生成目标格式。

    Args:
        md_path: Markdown 源文件路径
        target_format: 目标格式 pdf/docx/pptx

    Returns:
        转换结果 dict
    """
    import subprocess

    path = Path(md_path)
    ext_map = {"pdf": ".pdf", "docx": ".docx", "pptx": ".pptx"}
    ext = ext_map.get(target_format)
    if ext is None:
        return {
            "success": False,
            "output_path": None,
            "error": f"不支持的目标格式: {target_format}",
        }

    output_path = path.with_suffix(ext)

    result = subprocess.run(
        [
            "pandoc", str(path), "-f", "gfm",
            "-t", target_format, "-o", str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        return {
            "success": False,
            "output_path": None,
            "error": f"pandoc 反向转换失败: {result.stderr}",
        }

    return {
        "success": True,
        "output_path": str(output_path),
        "error": None,
    }
