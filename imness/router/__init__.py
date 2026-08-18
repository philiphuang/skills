"""imness router — 文档路由链。

两阶段:
  scan: 发现文档 → 过滤低重要性群 → 输出 AI prompt
  finalize: AI 响应 → 入待审池

CLI: python3 products/imness/router/route.py scan|finalize|review
"""
from .decision import Action, Decision, DocRef, DocType, RouteJudgment
from .context_loader import group_important, full_config, root
from .route import (
    PENDING_DIR, LOG_PATH,
    discover, ai_prompt, scan, finalize,
    write_pending, pending_list, review,
    accepted_list, process_accepted, mark_processed,
)

__all__ = [
    "Action", "Decision", "DocRef", "DocType", "RouteJudgment",
    "group_important", "full_config", "root",
    "PENDING_DIR", "LOG_PATH",
    "discover", "ai_prompt", "scan", "finalize",
    "write_pending", "pending_list", "review",
    "accepted_list", "process_accepted", "mark_processed",
]
