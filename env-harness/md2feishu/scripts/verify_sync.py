import argparse
import json
import re
import sys
from pathlib import Path


# 统计白板：<whiteboard ...> 出现次数（含 type="blank" 占位符和带 token 的真实白板）
_WHITEBOARD_RE = re.compile(r"<whiteboard\b[^>]*>", re.IGNORECASE)
# 统计图片：markdown ![alt](url) + XML <img ...>
_IMAGE_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_IMAGE_XML_RE = re.compile(r"<img\b[^>]*/?>", re.IGNORECASE)
# 统计章节：markdown ATX 标题行 ^#+（排除代码块内）
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+\S")


def _is_code_fence(line: str) -> bool:
    """判断是否为代码块围栏（``` 或 ~~~）。"""
    stripped = line.strip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def _track_code_block(content: str) -> list:
    """扫描内容行，返回每行是否在代码块内的布尔列表。"""
    lines = content.splitlines()
    in_block = False
    fence = ""
    result = []
    for line in lines:
        f = _is_code_fence(line)
        if f and not in_block:
            in_block = True
            fence = "```" if line.strip().startswith("```") else "~~~"
        elif f and in_block:
            in_block = False
            fence = ""
        result.append(in_block)
    return result


def count_whiteboards(content: str) -> int:
    """统计文档中白板数量（含占位符和真实白板）。"""
    return len(_WHITEBOARD_RE.findall(content))


def count_images(content: str) -> int:
    """统计图片数量（markdown 图片 + XML img 标签，去重避免重复计）。"""
    md_imgs = _IMAGE_MD_RE.findall(content)
    xml_imgs = _IMAGE_XML_RE.findall(content)
    return len(md_imgs) + len(xml_imgs)


def count_headings(content: str) -> int:
    """统计章节（标题）数量，排除代码块内。"""
    in_code_block = _track_code_block(content)
    lines = content.splitlines()
    return sum(
        1 for i, line in enumerate(lines)
        if not in_code_block[i] and _HEADING_RE.match(line)
    )


def count_comments(snapshot: dict) -> int:
    """从快照取批注数。优先 comments_count，否则 len(comments items)。"""
    if "comments_count" in snapshot:
        return snapshot["comments_count"]
    comments = snapshot.get("comments", [])
    if isinstance(comments, list):
        return len(comments)
    items = comments.get("items", []) if isinstance(comments, dict) else []
    return len(items)


def extract_doc_content(snapshot: dict) -> str:
    """从快照取文档内容（markdown 或 xml 字符串）。

    支持几种键：doc / content / markdown / data.document.content。
    """
    for key in ("doc", "content", "markdown"):
        if key in snapshot and isinstance(snapshot[key], str):
            return snapshot[key]
    data = snapshot.get("data", {})
    if isinstance(data, dict):
        doc = data.get("document", {})
        if isinstance(doc, dict) and "content" in doc:
            return doc["content"]
    return ""


def collect_counts(snapshot: dict) -> dict:
    """从一份快照收集四个维度的计数。"""
    content = extract_doc_content(snapshot)
    return {
        "comments": count_comments(snapshot),
        "whiteboards": count_whiteboards(content),
        "images": count_images(content),
        "headings": count_headings(content),
    }


def verify(before: dict, after: dict) -> dict:
    """对比同步前后四维计数，返回结构化校验结果。

    判定标准（工作法 §4.6）：
      - 批注数：after >= before（批注不能丢）
      - 白板数：after >= before
      - 图片数：after >= before
      - 章节数：after == before（章节结构应一致；新增章节是正常的，但不应减少）

    Returns:
        {"items": [...], "passed": bool, "failed_dims": [...]}
    """
    b = collect_counts(before)
    a = collect_counts(after)
    items = []

    # 批注、白板、图片：>=
    for dim in ("comments", "whiteboards", "images"):
        ok = a[dim] >= b[dim]
        items.append({
            "dim": dim, "before": b[dim], "after": a[dim], "passed": ok,
            "severity": "critical" if dim in ("comments", "whiteboards") else "warning",
        })

    # 章节：不减少（增加可能是新增章节，正常；减少说明结构被破坏）
    heading_ok = a["headings"] >= b["headings"]
    items.append({
        "dim": "headings", "before": b["headings"], "after": a["headings"],
        "passed": heading_ok, "severity": "warning",
    })

    failed = [it["dim"] for it in items if not it["passed"]]
    return {"items": items, "passed": len(failed) == 0, "failed_dims": failed}


def render_report(result: dict) -> str:
    """生成终端校验报告（工作法 §4.6 校验表格式）。"""
    lines = []
    lines.append("┌─────────────────────────────────────────┐")
    lines.append("│  同步后校验                              │")
    lines.append("├──────────────┬────────┬────────┬────────┤")
    lines.append("│  维度        │  同步前 │  同步后 │  结果  │".replace("维度        ", "维度        "))
    lines.append("├──────────────┼────────┼────────┼────────┤")

    dim_label = {
        "comments": "批注数", "whiteboards": "白板数",
        "images": "图片数", "headings": "章节数",
    }
    for it in result["items"]:
        label = dim_label.get(it["dim"], it["dim"])
        mark = "✅" if it["passed"] else ("❌" if it["severity"] == "critical" else "⚠️")
        lines.append(
            f"│  {label:<10} │  {it['before']:>5} │  {it['after']:>5} │  {mark}    │"
        )
    lines.append("└──────────────┴────────┴────────┴────────┘")

    if result["passed"]:
        lines.append("✅ 校验通过：批注/白板/图片/章节数量均未减少")
    else:
        critical = [it for it in result["items"]
                    if not it["passed"] and it["severity"] == "critical"]
        if critical:
            dims = "、".join(dim_label.get(i["dim"], i["dim"]) for i in critical)
            lines.append(f"❌ 校验失败：{dims}数量减少 — 可能误用了 overwrite 模式（工作法规则 1）")
        else:
            lines.append("⚠️ 校验警告：章节数量减少，请检查推送范围")
    return "\n".join(lines)


def load_snapshot(source: str) -> dict:
    """从文件路径或 stdin 加载 JSON 快照。"""
    if source == "-":
        text = sys.stdin.read()
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"快照文件不存在：{path}")
        text = path.read_text(encoding="utf-8")
    return json.loads(text)


def main():
    parser = argparse.ArgumentParser(
        description="同步后校验：对比前后快照的批注/白板/图片/章节数量（工作法 §4.6）"
    )
    parser.add_argument("--before", required=True,
                        help="同步前快照 JSON 文件（含 doc + comments_count）")
    parser.add_argument("--after", required=True,
                        help="同步后快照 JSON 文件（含 doc + comments_count）")
    args = parser.parse_args()

    try:
        before = load_snapshot(args.before)
        after = load_snapshot(args.after)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"错误：加载快照失败：{e}", file=sys.stderr)
        sys.exit(2)

    result = verify(before, after)
    print(render_report(result))

    # 同时输出结构化 JSON 到 stderr，便于 agent 解析
    print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
