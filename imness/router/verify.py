"""verify.py — 路由链各节点的数据质量验证。

三个验证点：
  1. 路由输入验证: 消息、文档引用的格式合法性
  2. 待审池验证: pending 文件 frontmatter 完整性
  3. 配置验证: mywork.config.md 格式正确性
"""
import json
import re
from pathlib import Path

from .context_loader import root
from ._shared import parse_fm


def verify_messages(messages: list[dict]) -> list[str]:
    """每个消息必须含 chat_name, chat_id, content。"""
    if not isinstance(messages, list):
        return ["消息输入必须是列表"]
    issues: list[str] = []
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            issues.append(f"[msg #{i}] 不是 dict"); continue
        for k in ("chat_name", "chat_id", "content"):
            if k not in m:
                issues.append(f"[msg #{i}] 缺少 {k}")
    return issues


def verify_doc_ref(doc: dict) -> list[str]:
    issues: list[str] = []
    if not doc.get("url"): issues.append("doc.url 为空")
    if not doc.get("source_chat"): issues.append("doc.source_chat 为空")
    return issues


def verify_ai_response(resp: dict) -> list[str]:
    issues: list[str] = []
    for k in ("doc_type", "should_process", "reason"):
        if k not in resp:
            issues.append(f"AI 响应缺少 {k}")
    if "should_process" in resp and not isinstance(resp["should_process"], bool):
        issues.append("should_process 必须是 bool")
    return issues


def verify_pending_file(path: Path) -> list[str]:
    if not path.exists():
        return [f"文件不存在: {path}"]
    issues: list[str] = []
    text = path.read_text()
    for k in ("source_chat", "status", "url"):
        if not re.search(rf'^{k}:', text, re.M):
            issues.append(f"待审文件 {path.name} 缺少 {k}")
    m = re.search(r'^status:\s*(\w+)', text, re.M)
    if m and m.group(1) not in ("pending", "accepted", "rejected"):
        issues.append(f"待审文件 {path.name} status 非法: {m.group(1)}")
    return issues


def verify_config() -> list[str]:
    p = root() / "knowledge" / "mywork.config.md"
    if not p.exists():
        return ["knowledge/mywork.config.md 不存在"]
    issues: list[str] = []
    text = p.read_text()
    if "## 群组重要性" not in text:
        issues.append("缺少 ## 群组重要性 段")
    if "## 当前工作" not in text:
        issues.append("缺少 ## 当前工作 段")
    if any(re.match(r'^-\s*\*\*.+?\*\*\s*—\s*(high|low)\s*:', l) for l in text.split("\n")):
        pass  # ok
    elif "## 群组重要性" in text:
        issues.append("群组重要性段下没有合法的群组条目")
    return issues


def verify_pending_batch() -> tuple[list[dict], list[str]]:
    pd = root() / "knowledge" / "pending-docs"
    if not pd.exists():
        return [], []
    valid: list[dict] = []
    issues: list[str] = []
    for f in sorted(pd.glob("*.md")):
        file_issues = verify_pending_file(f)
        if file_issues:
            issues.extend(file_issues)
        else:
            fm = parse_fm(f.read_text())
            valid.append({"file": f.name, "status": fm.get("status", "unknown")})
    return valid, issues


# === CLI ===

def main() -> None:
    import argparse, sys
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("config"); sub.add_parser("pending")
    sub.add_parser("messages"); sub.add_parser("ai-response")
    args = ap.parse_args()

    icon = {"pending":"⏳","accepted":"✅","rejected":"❌"}

    if args.cmd == "config":
        issues = verify_config()
        if issues: [print(f"❌ {i}") for i in issues]
        else: print("✅ knowledge/mywork.config.md 格式正确")

    elif args.cmd == "pending":
        valid, issues = verify_pending_batch()
        if valid:
            print(f"✅ 有效待审文件: {len(valid)}")
            for v in valid:
                s = v["status"]
                print(f"  {icon.get(s,'?')} [{s}] {v['file']}")
        [print(f"❌ {i}") for i in issues]
        if not valid and not issues: print("待审池为空")

    elif args.cmd == "messages":
        data = json.loads(sys.stdin.read())
        issues = verify_messages(data)
        if issues: [print(f"❌ {i}") for i in issues]
        else: print(f"✅ {len(data)} 条消息格式正确")

    elif args.cmd == "ai-response":
        data = json.loads(sys.stdin.read())
        issues = verify_ai_response(data)
        if issues: [print(f"❌ {i}") for i in issues]
        else: print("✅ AI 响应格式正确")

    else:
        ap.print_help()


if __name__ == "__main__":
    main()
