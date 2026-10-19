"""结构化运行报告（#109 §4 / #110 §5：会话尾部呈现，天然告警通道）。"""
from __future__ import annotations

BACKLOG_WARN = 5


def build_report(stats: dict) -> str:
    lines = ["=== 千问纪要同步运行报告 ==="]
    lines.append(
        f"新增纪要 {stats['pulled']}（归档 {stats['archived']} / 待分拣 {stats['inboxed']} / "
        f"已存在跳过 {stats['skipped']}）；待分拣重扫归档 {stats['rescanned']}"
    )
    lines.append(f"Cookie 探活: {'OK' if stats['cookie_ok'] else 'FAIL'}")
    if stats["inbox_titles"]:
        lines.append("待分拣清单:")
        lines += [f"  - {t}" for t in stats["inbox_titles"]]
    if stats["backlog"] > BACKLOG_WARN:
        lines.append(f"⚠️ 待分拣积压 {stats['backlog']} 条（>{BACKLOG_WARN}）：重跑 gen_projects_map --dir /opt/prjs 或手工补映射条目后重跑本管线")
    if stats["llm_tasks"]:
        verb = "将写入" if stats.get("dry_run") else "已写入"
        lines.append(f"待 LLM 判定 {len(stats['llm_tasks'])} 条：ai_prompt {verb} {stats['llm_tasks_path']}")
        lines.append("  automation agent 判定后执行: qianwen_sync.py finalize --answers <answers.json>")
    if stats["errors"]:
        lines.append("错误:")
        lines += [f"  - {e}" for e in stats["errors"]]
    return "\n".join(lines)


def cookie_fail_report(message: str) -> str:
    return "\n".join([
        "=== 千问纪要同步运行报告 ===",
        f"Cookie 探活: FAIL — {message}",
        "需人工续期：浏览器登录 www.qianwen.com 后更新 Cookie 快照（#107：不自动重试、不写 state）",
    ])
