"""附件 / 嵌入对象 / 外部链接提取器。

检测来源：
  旧格式 (.doc/.ppt/.xls/.wps): olefile 直接解析原始文件的 OLE ObjectPool/{id}/package 流。
    注意：LibreOffice 桥接后的新格式会丢失大部分嵌入对象（实测 10 个只剩 1 个），
    提取嵌入附件必须解析原始旧格式文件，不能依赖转换产物。
  新格式 (.docx/.pptx/.xlsx): zip 解包扫描 */embeddings/，并解析 */_rels/*.rels 中
    TargetMode="External" 的 hyperlink 得到外部 URL（在线文档线索）。

用法（CLI，从 docness 目录执行）:
  python3 -m scripts.extract_attachments <文件路径> [--outdir <附件目录>]

  --outdir 缺省为 <文件所在目录>/<文件名去后缀>/；collect SOP 中应传
  工作台/{正文名去后缀}/（工作台取 init_workspace 输出的绝对路径）。

输出 JSON:
  {
    "success": bool,
    "attachments_dir": str | None,
    "attachments": [{"filename", "path", "type", "title", "md5", "size", "refs"}],
    "external_urls": [{"url", "refs"}],
    "urls_file": str | None,
    "notes": [str],
    "error": str | None,
  }

处理范围与去重：
  - 只落「需进一步处理的附件」：docx/xlsx/pptx/pdf。图片（png/jpg/emf 等）不在此阶段落盘——
    由转换阶段（pandoc/MinerU）从源文档提取 media，避免双份处理与源目录污染。
  - 附件以可识别命名落位：标题（docProps/core.xml 的 <dc:title>）优先；
    无标题退回 "附件N" 占位，SOP 要求随后从正文首行/标题提炼真实文件名补名，
    禁止以 "嵌入附件N" 占位交付。
  - 与附件目录已有文件 md5 一致（无论文件名，如命名附件与 OLE 嵌入同文件）不重复剥离。

依赖：olefile（pip3 install olefile，解析旧格式与 oleObject*.bin 时必需）。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"
PDF_MAGIC = b"%PDF"

# Office Open XML 类型特征路径 → 扩展名
OOXML_SIGNATURES = [
    ("word/document.xml", ".docx"),
    ("xl/workbook.xml", ".xlsx"),
    ("ppt/presentation.xml", ".pptx"),
]

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.]+$")


def identify_payload(data: bytes) -> dict:
    """识别嵌入对象字节流的类型与标题。

    三板斧：魔数 → Office 类型特征路径 → docProps/core.xml 的 <dc:title>。
    返回 {"ext": ".docx"|".xlsx"|".pptx"|".pdf"|".bin", "title": str | None}
    """
    if data[: len(PDF_MAGIC)] == PDF_MAGIC:
        return {"ext": ".pdf", "title": None}

    if data[: len(ZIP_MAGIC)] == ZIP_MAGIC:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
                for signature, ext in OOXML_SIGNATURES:
                    if signature in names:
                        return {"ext": ext, "title": _read_core_title(zf)}
        except zipfile.BadZipFile:
            pass
        return {"ext": ".zip", "title": None}

    if data[: len(OLE_MAGIC)] == OLE_MAGIC:
        # 旧 OLE 复合文档（.doc/.xls/.ppt 或 oleObject 容器）
        return {"ext": ".bin", "title": None}

    return {"ext": ".bin", "title": None}


def _read_core_title(zf: zipfile.ZipFile) -> str | None:
    """从 docProps/core.xml 读 <dc:title>，用于确认附件身份并命名。"""
    try:
        raw = zf.read("docProps/core.xml")
    except KeyError:
        return None
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None
    for elem in root.iter():
        if elem.tag.endswith("}title") and elem.text and elem.text.strip():
            return elem.text.strip()
    return None


def is_bogus_mailto(target: str) -> bool:
    """甄别"误标 mailto"：目标不是合法邮箱地址即视为正文文字误设链接，应排除。"""
    if not target.lower().startswith("mailto:"):
        return False
    address = target[7:].split("?")[0]
    return not EMAIL_RE.match(address)


def _sanitize_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()[:80]


def _payloads_from_ole(ole) -> list[bytes]:
    """读取 OLE 复合文档中 ObjectPool/{id}/package 流（package 流即原始文件字节）。"""
    payloads = []
    for entry in ole.listdir():
        # entry 形如 ["ObjectPool", "_1234567890", "package"]
        if len(entry) >= 2 and entry[0] == "ObjectPool" and entry[-1].lower() == "package":
            payloads.append(ole.openstream(entry).read())
    return payloads


def _open_ole(source):
    """惰性导入 olefile 并打开 OLE 复合文档（路径或字节流）。"""
    try:
        import olefile
    except ImportError as e:
        raise RuntimeError(
            "olefile 未安装，无法解析嵌入对象；请执行 pip3 install olefile"
        ) from e
    return olefile.OleFileIO(source)


def _scan_legacy(path: Path) -> tuple[list[bytes], list[dict], list[str]]:
    """旧格式：直接解析原始文件的 OLE ObjectPool（外部链接需桥接后另行提取）。"""
    notes = [
        "旧格式文件的外部链接（在线文档 URL）需先经 LibreOffice 桥接为新格式后再提取"
    ]
    try:
        with _open_ole(str(path)) as ole:
            return _payloads_from_ole(ole), [], notes
    except RuntimeError:
        raise
    except Exception as e:
        return [], [], notes + [f"OLE 解析失败（可能不是复合文档）: {e}"]


def _scan_ooxml(path: Path) -> tuple[list[bytes], list[dict], list[str]]:
    """新格式：扫描 */embeddings/ + 解析 */_rels/*.rels 外部链接。"""
    payloads: list[bytes] = []
    urls: list[dict] = []
    notes: list[str] = []

    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if "/embeddings/" in name and not name.endswith("/"):
                data = zf.read(name)
                if data[: len(OLE_MAGIC)] == OLE_MAGIC:
                    # oleObject*.bin 是 OLE 容器，附件字节在其 package 流中
                    try:
                        with _open_ole(io.BytesIO(data)) as ole:
                            payloads.extend(_payloads_from_ole(ole))
                    except RuntimeError:
                        raise
                    except Exception:
                        payloads.append(data)  # 保底：原样保留
                else:
                    payloads.append(data)
            elif name.endswith(".rels") and "/_rels/" in name:
                urls.extend(_parse_rels(zf.read(name)))

    return payloads, urls, notes


def _parse_rels(raw: bytes) -> list[dict]:
    """解析 .rels 中 TargetMode="External" 的 hyperlink 关系。

    ElementTree 会自动还原 `&amp;` 等 XML 转义，无需手工处理。
    """
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return []
    urls = []
    for rel in root:
        if not rel.tag.endswith("}Relationship"):
            continue
        if rel.get("TargetMode") != "External":
            continue
        if not rel.get("Type", "").endswith("/hyperlink"):
            continue
        target = rel.get("Target", "")
        if not target or is_bogus_mailto(target):
            continue
        urls.append({"url": target})
    return urls


def _dedup_payloads(payloads: list[bytes]) -> list[dict]:
    """按 md5 去重；重复附件只保留一份，refs 记录文中引用次数。"""
    seen: dict[str, dict] = {}
    order: list[str] = []
    for data in payloads:
        digest = hashlib.md5(data).hexdigest()
        if digest in seen:
            seen[digest]["refs"] += 1
            continue
        seen[digest] = {"data": data, "md5": digest, "refs": 1}
        order.append(digest)
    return [seen[d] for d in order]


def _payload_digest(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _is_decorative_image(filename: str, data: bytes) -> bool:
    """装饰性小文件丢弃判定：emf/wmf 矢量图（有 png 副本时冗余）、<5KB 小图标。

    文件名与字节共同判定。提取阶段不做此判定（图片不落盘，由转换阶段按
    sops/collect.md「media 规则」处理），此函数保留给转换阶段复用。
    """
    name_lower = filename.lower()
    if name_lower.endswith((".emf", ".wmf")):
        return True
    if len(data) < 5 * 1024 and name_lower.endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp")
    ):
        return True
    return False


def _dedup_urls(urls: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    order: list[str] = []
    for item in urls:
        url = item["url"]
        if url in seen:
            seen[url]["refs"] += 1
            continue
        seen[url] = {"url": url, "refs": 1}
        order.append(url)
    return [seen[u] for u in order]


def rename_attachment(attachments_dir: str | Path, old_name: str, new_name: str) -> str | None:
    """给剥离出的附件补可识别命名（如从正文首行/标题提炼的真实文件名）。

    原文件可能是 "附件N" 占位（无标题）或 "附件N_标题" 形式；落位同目录，
    文件名安全化（非法字符 → _）。返回新文件路径；旧文件不存在或已同名返回 None。

    注意：重命名后需同步更新 知识库 md / media 目录 / md 内引用 / 索引 source /
    主文档附件清单（5 处），见 sops/collect.md「附件与在线文档」。
    """
    out = Path(attachments_dir)
    old = out / old_name
    if not old.exists():
        return None
    new_name = _sanitize_name(new_name)
    new = out / new_name
    if new.exists():
        return str(new)
    old.rename(new)
    return str(new)


def extract_attachments(filepath: str | Path, outdir: str | Path | None = None) -> dict:
    """提取文件中的嵌入附件与外部链接。

    Args:
        filepath: 原始文件路径（旧格式直接解析，新格式解包扫描）
        outdir: 附件输出目录，缺省为 <文件所在目录>/<文件名去后缀>/
    """
    path = Path(filepath)
    if not path.exists():
        return _error(f"文件不存在: {path}")

    file_type = path.suffix.lower()
    try:
        if file_type in {".doc", ".ppt", ".xls", ".wps"}:
            payloads, urls, notes = _scan_legacy(path)
        elif file_type in {".docx", ".pptx", ".xlsx"}:
            payloads, urls, notes = _scan_ooxml(path)
        else:
            return _error(f"不支持附件提取的文件类型: {file_type or '(无后缀)'}")
    except RuntimeError as e:
        return _error(str(e))
    except zipfile.BadZipFile:
        return _error(f"不是有效的 zip/OOXML 文件: {path.name}")

    unique = _dedup_payloads(payloads)
    unique_urls = _dedup_urls(urls)

    if not unique and not unique_urls:
        return {
            "success": True,
            "attachments_dir": None,
            "attachments": [],
            "external_urls": [],
            "urls_file": None,
            "notes": notes + ["未发现嵌入附件或外部链接"],
            "error": None,
        }

    out = Path(outdir) if outdir else path.parent / path.stem
    out.mkdir(parents=True, exist_ok=True)

    # 目录内已有文件 md5 集合（供跨文件名去重，循环前一次计算）
    existing_digests = {_payload_digest(p.read_bytes()) for p in out.iterdir() if p.is_file()}

    # 附件提取阶段只落「需进一步处理的附件」：docx/xlsx/pptx/pdf。
    # 图片（png/jpg/emf 等）不在此阶段落盘——由转换阶段（pandoc/MinerU）从源文档
    # 提取 media（见 sops/collect.md「media 规则」），避免双份处理与源目录污染。
    PROCESSABLE_EXTS = {".docx", ".xlsx", ".pptx", ".pdf"}

    attachments = []
    skipped_notes: list[str] = []
    for i, item in enumerate(unique, 1):
        info = identify_payload(item["data"])
        title = _sanitize_name(info["title"]) if info["title"] else ""
        # 可识别命名优先：真实标题（docProps/core.xml 的 <dc:title>）作为文件名；
        # 无标题才退回 "附件N" 占位（此时 SOP 要求从正文首行/标题提炼后补名）。
        filename = f"{title}{info['ext']}" if title else f"附件{i}{info['ext']}"
        if info["ext"] not in PROCESSABLE_EXTS:
            skipped_notes.append(
                f"跳过非处理附件 {filename}（{info['ext']}，图片/其他类型由转换阶段提取 media）"
            )
            continue
        target = out / filename
        # 与附件目录已有文件 md5 一致（无论文件名）→ 不重复剥离（如命名附件与 OLE 嵌入同文件）
        if item["md5"] in existing_digests:
            continue
        target.write_bytes(item["data"])
        attachments.append(
            {
                "filename": filename,
                "path": str(target),
                "type": info["ext"].lstrip("."),
                "title": info["title"],
                "md5": item["md5"],
                "size": len(item["data"]),
                "refs": item["refs"],
            }
        )

    urls_file = None
    if unique_urls:
        lines = ["# 外部 URL", ""]
        for item in unique_urls:
            suffix = f"（文中引用 {item['refs']} 次）" if item["refs"] > 1 else ""
            lines.append(f"- {item['url']}{suffix}")
        urls_path = out / "外部URL.md"
        urls_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        urls_file = str(urls_path)

    return {
        "success": True,
        "attachments_dir": str(out),
        "attachments": attachments,
        "external_urls": unique_urls,
        "urls_file": urls_file,
        "notes": notes + skipped_notes,
        "error": None,
    }


def _error(message: str) -> dict:
    return {
        "success": False,
        "attachments_dir": None,
        "attachments": [],
        "external_urls": [],
        "urls_file": None,
        "notes": [],
        "error": message,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="提取文档中的嵌入附件与外部链接")
    parser.add_argument("filepath", help="原始文件路径（.doc/.docx/.ppt/.pptx/.xls/.xlsx/.wps）")
    parser.add_argument("--outdir", help="附件输出目录（缺省：<文件所在目录>/<文件名去后缀>/）")
    args = parser.parse_args()

    result = extract_attachments(args.filepath, args.outdir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
