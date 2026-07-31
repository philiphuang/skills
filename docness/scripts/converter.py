"""文档转换编排器——根据复杂度判定结果，路由到对应转换工具链。

工具链总图：
  simple: pandoc (DOCX/PPTX/PDF) / pypdf (PDF) / pandas+openpyxl (Excel) → Markdown
  complex: MinerU Skill → 高精度 Markdown
  旧格式 (.doc/.ppt/.xls/.wps): LibreOffice headless → 新格式 → 继续

反向:
  pandoc: Markdown → PDF/DOCX/PPTX
  pandas: CSV/DataFrame → XLSX
"""

from __future__ import annotations

from pathlib import Path

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


def _simple_excel(path: Path) -> dict:
    """pandas+openpyxl 转换 Excel → Markdown 表格。"""
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
        xlsx = pd.ExcelFile(str(path), engine="openpyxl")
    except Exception as e:
        return {
            "success": False,
            "output_path": None,
            "content": None,
            "route": "simple",
            "tool": "pandas",
            "error": f"无法读取 Excel 文件: {e}",
        }

    parts = [f"# {path.stem}\n"]
    for sheet_name in xlsx.sheet_names:
        df = pd.read_excel(xlsx, sheet_name=sheet_name)
        parts.append(f"## {sheet_name}\n")
        parts.append(df.to_markdown(index=False))
        parts.append("")

    content = "\n".join(parts)
    output_path = path.with_suffix(".md")
    output_path.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "output_path": str(output_path),
        "content": content,
        "route": "simple",
        "tool": "pandas+openpyxl",
        "error": None,
    }


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
