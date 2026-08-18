"""scan_runner — 安全执行扫描的引导脚本。

用法: cat messages.json | python3 products/imness/router/scan_runner.py [--write]

从项目根目录执行，自动解决 relative import 问题。
"""
import json, os, sys

# 切换到项目根
project_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(project_root, "CLAUDE.md")):
    parent = os.path.dirname(project_root)
    if parent == project_root:
        print("错误: 找不到项目根 (CLAUDE.md)", file=sys.stderr); sys.exit(1)
    project_root = parent

os.chdir(project_root)
sys.path.insert(0, project_root)

from products.imness.router import scan, finalize, write_pending, review, process_accepted, mark_processed, DocRef

write_flag = "--write" in sys.argv

msgs = json.loads(sys.stdin.read())
results = scan(msgs)

needs_ai = 0
for r in results:
    if r["decision"] == "skipped":
        print("SKIP: " + r["doc"].get("source_chat","") + " - " + r["reason"])
    else:
        needs_ai += 1
        print("")
        print("=== NEEDS AI ===")
        print("source: " + r["doc"].get("source_chat","") + "  url: "
              + r["doc"].get("url",""))
        print(r["ai_prompt"])
        print("---END PROMPT---")

print("")
print("总计: " + str(len(results)) + " 个文档, "
      + str(needs_ai) + " 待AI, "
      + str(len(results) - needs_ai) + " 跳过")
