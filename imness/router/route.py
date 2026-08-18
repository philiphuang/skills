"""route.py — 文档路由编排器。

两阶段:
  scan: 群消息 → 发现文档 → 过滤低重要性群 → 输出 AI prompt
  finalize: AI 响应 → 写入待审池

CLI:
  python3 products/imness/router/route.py scan < messages.json
  python3 products/imness/router/route.py finalize '<json>'
  python3 products/imness/router/route.py review list|accept|reject
"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from ._shared import parse_fm
from .context_loader import group_important, full_config, root
from .decision import Action, Decision, DocRef, DocType, RouteJudgment

PENDING_DIR = root() / "knowledge" / "pending-docs"
LOG_PATH = root() / "knowledge" / "router-log.jsonl"

_DOC_URL_RE = re.compile(
    r'https?://[\w.-]*('
    r'feishu\.cn|bytedance\.net|larksuite\.com|'
    r'docs?\.qq\.com|doc\.weixin\.qq\.com|'
    r'notion\.so|yuque\.com|shimo\.im|'
    r'wiki|confluence|gitbook'
    r')[/\w?=&%#@.+~!*\'\"()\[\]-]*'
)
_ATTACH_RE = re.compile(r'(?:file_key|file_id|attachment)[=:]\s*[\"\']?([\w.-]+)')
_FILENAME_RE = re.compile(r'(?:文件名|文档名)[:：]\s*(.+?)(?:\s|$)', re.I)

_ICON = {"pending": "⏳", "accepted": "✅", "rejected": "❌"}


# === 阶段A ===

def discover(messages: list[dict]) -> list[DocRef]:
    """从消息列表提取文档引用（只匹配文档平台 URL）。"""
    docs: list[DocRef] = []
    seen: set[str] = set()
    for msg in messages:
        content = msg.get("content", "")
        cn, cid = msg.get("chat_name", ""), msg.get("chat_id", "")
        for m in _DOC_URL_RE.finditer(content):
            u = m.group(0)
            if u in seen: continue
            seen.add(u)
            docs.append(DocRef(url=u, doc_type=DocType.ONLINE, source_chat=cn,
                              source_chat_id=cid, context_snippet=content[:300]))
        for m in _ATTACH_RE.finditer(content):
            key = m.group(1)
            fn = _FILENAME_RE.search(content)
            docs.append(DocRef(url=f"attachment:{key}",
                              filename=fn.group(1).strip() if fn else "",
                              doc_type=DocType.ATTACHMENT,
                              source_chat=cn, source_chat_id=cid,
                              context_snippet=content[:300]))
    return docs


def ai_prompt(doc: DocRef) -> str:
    """构建给 AI 的文档价值判断 prompt。"""
    cfg = full_config()
    return f"""你是文档路由助手。判断 IM 群聊中发现的文档是否需要处理。

## 工作配置

{cfg if cfg else "（未配置 knowledge/mywork.config.md）"}

## 文档

- 来源群: {doc.source_chat}
- 链接: {doc.url}
- 文件名: {doc.filename or "—"}
- 上下文: {doc.context_snippet or "（无）"}

返回 JSON（不加 markdown 代码块）:
{{"doc_type":"识别出的文档类型","should_process":true/false,"reason":"一句话判断理由"}}
"""


def scan(messages: list[dict]) -> list[dict]:
    """阶段A: 发现文档 → 过滤低重要性群 → 输出 AI prompt。"""
    docs = discover(messages)
    results: list[dict] = []
    for doc in docs:
        ok, reason = group_important(doc.source_chat)
        if not ok:
            _log(Decision(doc=doc, action=Action.SKIPPED,
                          summary=f"跳过 (群重要性低): {reason}"))
            results.append({"decision": "skipped", "doc": doc.to_dict(), "reason": reason})
        else:
            results.append({"decision": "needs_ai", "doc": doc.to_dict(),
                           "ai_prompt": ai_prompt(doc)})
    return results


# === 阶段B ===

def finalize(doc: DocRef, ai_response: dict) -> Decision:
    """阶段B: AI 响应 → Decision。"""
    should = ai_response.get("should_process", False)
    reason = ai_response.get("reason", "")
    dtype = ai_response.get("doc_type", "")

    d = Decision(
        doc=doc,
        judgment=RouteJudgment(doc_type_name=dtype, should_process=should, reason=reason),
        action=Action.APPROVED if should else Action.SKIPPED,
        summary=f"✅ {doc.source_chat} → {dtype}: {reason}" if should
                else f"⏭️ 跳过: {reason}",
    )
    _log(d)
    return d


# === 待审池 ===

def _pending_frontmatter(doc: DocRef, dtype: str) -> str:
    return "\n".join([
        "---",
        f"source_chat: {doc.source_chat}",
        f"source_chat_id: {doc.source_chat_id}",
        "status: pending",
        f"url: {doc.url}",
        f"filename: {doc.filename}",
        f"doc_type: {dtype}",
        "reviewed_at: \"\"",
        "---",
    ])


def write_pending(d: Decision) -> Optional[Path]:
    if d.action != Action.APPROVED or not d.doc:
        return None
    os.makedirs(PENDING_DIR, exist_ok=True)
    doc = d.doc
    ts = datetime.now(tz=timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    sid = re.sub(r'[^\w.-]', '_', doc.url[:40] or "unknown")
    p = PENDING_DIR / f"{ts}-{sid}.md"
    p.write_text(f"""{_pending_frontmatter(doc, d.judgment.doc_type_name)}
# {d.judgment.doc_type_name or '文档'}

**来源**: {doc.source_chat}
**链接**: {doc.url}
**AI 判断**: {d.judgment.reason}

## 上下文

{doc.context_snippet or "（无）"}

## 审核

修改 frontmatter status 为 `accepted`（通过）或 `rejected`（拒绝）
""")
    return p


def _log(d: Decision) -> None:
    os.makedirs(LOG_PATH.parent, exist_ok=True)
    rec = d.to_dict()
    rec["timestamp"] = datetime.now(tz=timezone(timedelta(hours=8))).isoformat()
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# === 审核 ===

def pending_list() -> list[dict]:
    if not PENDING_DIR.exists():
        return []
    result = []
    for f in sorted(PENDING_DIR.glob("*.md")):
        front = parse_fm(f.read_text())
        result.append({"file": f.name, **front})
    return result


def review(action: str, filename: str) -> bool:
    p = PENDING_DIR / filename
    if not p.exists():
        print(f"不存在: {p}")
        return False
    text = p.read_text()
    ts = datetime.now(tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    text = re.sub(r'^status:\s*\w+', f'status: {action}', text, flags=re.M)
    text = re.sub(r'^reviewed_at:\s*""', f'reviewed_at: "{ts}"', text, flags=re.M)
    p.write_text(text)
    return True


# === docness 收录 ===

def accepted_list() -> list[dict]:
    """扫描已审核通过、待 docness 处理的文件。"""
    return [i for i in pending_list() if i.get("status") == "accepted"]


def process_accepted() -> list[dict]:
    """扫描 accepted 状态的文件，输出 docness 收录指令给 agent。

    返回每条的: source_chat, url, filename, doc_type, file
    agent 根据 doc_type 决定:
      - online → 传 url 给 docness
      - attachment → 先下载附件再喂 docness
    """
    items = accepted_list()
    results = []
    for item in items:
        path = PENDING_DIR / item["file"]
        text = path.read_text()
        fm = parse_fm(text)

        # 提取上下文
        ctx = ""
        m = re.search(r'## 上下文\n\n(.+?)(?:\n## |$)', text, re.S)
        if m:
            ctx = m.group(1).strip()

        results.append({
            "file": item["file"],
            "url": fm.get("url", ""),
            "filename": fm.get("filename", ""),
            "doc_type": fm.get("doc_type", ""),
            "source_chat": fm.get("source_chat", ""),
            "context_snippet": ctx[:300],
            "action": "fetch_attachment" if fm.get("url", "").startswith("attachment:")
                      else "docness_collect",
        })
    return results


def mark_processed(filename: str) -> bool:
    """docness 收录完成后标记文件为 processed。"""
    p = PENDING_DIR / filename
    if not p.exists():
        return False
    text = p.read_text()
    ts = datetime.now(tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    text = re.sub(r'^status:\s*\w+', 'status: processed', text, flags=re.M)
    text = re.sub(r'^reviewed_at:\s*"(.*)"',
                  f'reviewed_at: "\\1\\nprocessed_at: \\"{ts}\\"', text, flags=re.M)
    p.write_text(text)
    return True


# === CLI ===

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")

    sp = sub.add_parser("scan"); sp.add_argument("--log", action="store_true")
    fp = sub.add_parser("finalize"); fp.add_argument("input_json")

    rp = sub.add_parser("review")
    rs = rp.add_subparsers(dest="review_action")
    rs.add_parser("list")
    for a in ("accept", "reject"):
        p = rs.add_parser(a); p.add_argument("file")

    args = ap.parse_args()

    if args.cmd == "scan":
        msgs = json.loads(sys.stdin.read())
        results = scan(msgs)
        for r in results:
            if r["decision"] == "skipped":
                print(f"⏭️ 跳过: {r['doc'].get('source_chat','')} — {r['reason']}")
            else:
                print(f"\n=== 待审核 ===")
                print(f"来源: {r['doc'].get('source_chat','')}  链接: {r['doc'].get('url','')}")
                print(r["ai_prompt"])
        print(f"\n总计: {len(results)} 个文档, "
              f"{sum(1 for r in results if r['decision']=='needs_ai')} 待AI, "
              f"{sum(1 for r in results if r['decision']=='skipped')} 跳过")

    elif args.cmd == "finalize":
        data = json.loads(args.input_json)
        dd = data["doc"]
        doc = DocRef(url=dd.get("url",""), filename=dd.get("filename",""),
                     doc_type=DocType(dd.get("doc_type","online")),
                     source_chat=dd.get("source_chat",""), source_chat_id=dd.get("source_chat_id",""),
                     context_snippet=dd.get("context_snippet",""))
        d = finalize(doc, data["ai_response"])
        print(d.summary)
        if d.action == Action.APPROVED:
            p = write_pending(d)
            if p: print(f"  待审池: {p.name}")

    elif args.cmd == "review" and args.review_action == "list":
        items = pending_list()
        if not items: print("待审池为空"); return
        print(f"待审文档 {len(items)} 个:\n")
        for i in items:
            status = i.get("status", "pending")
            print(f"  {_ICON.get(status, '?')} [{status}] {i.get('source_chat','')} — {i.get('doc_type','')}")
            print(f"     {i.get('url','')[:80]}\n     {i['file']}\n")

    elif args.cmd == "review" and args.review_action in ("accept","reject"):
        ok = review("accepted" if args.review_action=="accept" else "rejected", args.file)
        if ok: print(f"{'✅' if args.review_action=='accept' else '❌'} {args.file}")

    elif args.cmd == "review" and args.review_action == "pending":
        pass

    elif args.cmd == "process":
        items = process_accepted()
        if not items:
            print("没有待 docness 处理的文档"); return
        print(f"待 docness 收录: {len(items)} 个\n")
        for item in items:
            print(f"  📄 [{item['doc_type']}] {item['source_chat']}")
            print(f"     url: {item['url'][:80]}")
            print(f"     action: {item['action']}")
            if item['action'] == 'fetch_attachment':
                print(f"     文件名: {item['filename']}")
            print(f"     file: {item['file']}")
            print(f"     上下文: {item['context_snippet'][:100]}\n")

    elif args.cmd == "mark-processed":
        # parse from remaining argv: python3 route.py mark-processed <file>
        import argparse as _ap
        mp = _ap.ArgumentParser()
        mp.add_argument("command"); mp.add_argument("file")
        na = mp.parse_known_args(sys.argv[1:])[0]
        if mark_processed(na.file):
            print(f"✅ processed: {na.file}")

    else:
        ap.print_help()


if __name__ == "__main__":
    main()
