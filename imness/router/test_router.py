"""router 模块单元测试。"""
from .context_loader import group_important, full_config
from .decision import Action, Decision, DocRef, DocType, RouteJudgment
from .route import (
    discover, ai_prompt, scan, finalize,
    write_pending, pending_list, review,
)


def test_group_important_high() -> None:
    ok, _ = group_important("产品群-核心讨论组")
    assert ok


def test_group_important_low() -> None:
    assert not group_important("公司大群")[0]


def test_group_important_unknown() -> None:
    ok, reason = group_important("随机群")
    assert not ok and "未在配置中" in reason


def test_full_config() -> None:
    assert "群组重要性" in full_config()


def test_discover_doc_url() -> None:
    docs = discover([{"chat_name":"T","chat_id":"x",
                      "content":"PRD https://xxx.feishu.cn/docx/abc"}])
    assert len(docs) == 1 and docs[0].doc_type == DocType.ONLINE


def test_discover_dedup() -> None:
    docs = discover([
        {"chat_name":"T","chat_id":"x","content":"https://xxx.feishu.cn/doc"},
        {"chat_name":"T","chat_id":"x","content":"https://xxx.feishu.cn/doc"},
    ])
    assert len(docs) == 1


def test_discover_attachment() -> None:
    docs = discover([{"chat_name":"T","chat_id":"x",
                      "content":"附件 file_key: report.pdf"}])
    assert len(docs) == 1 and docs[0].doc_type == DocType.ATTACHMENT


def test_discover_ignores_generic() -> None:
    assert discover([{"chat_name":"T","chat_id":"x",
                      "content":"团建 https://event.com/signup"}]) == []


def test_scan_important() -> None:
    r = scan([{"chat_name":"产品群-核心","chat_id":"A",
               "content":"PRD https://xxx.feishu.cn/docx/test"}])
    assert r[0]["decision"] == "needs_ai"


def test_scan_low() -> None:
    r = scan([{"chat_name":"公司大群","chat_id":"B",
               "content":"通知 https://xxx.feishu.cn/docx/notice"}])
    assert r[0]["decision"] == "skipped"


def test_finalize_approve() -> None:
    d = finalize(DocRef(url="https://x.com/doc", source_chat="产品群-核心"),
                 {"doc_type":"PRD","should_process":True,"reason":"match"})
    assert d.action == Action.APPROVED


def test_finalize_skip() -> None:
    d = finalize(DocRef(url="https://x.com/doc", source_chat="产品群-核心"),
                 {"doc_type":"团建","should_process":False,"reason":"不相关"})
    assert d.action == Action.SKIPPED


def test_write_and_list_pending() -> None:
    d = Decision(
        doc=DocRef(url="https://feishu.cn/docx/test", source_chat="产品群-核心", source_chat_id="oc_x"),
        judgment=RouteJudgment(doc_type_name="PRD", should_process=True, reason="match"),
        action=Action.APPROVED,
    )
    p = write_pending(d)
    assert p and p.exists() and "status: pending" in p.read_text()
    assert any(i["file"] == p.name for i in pending_list())


def test_write_pending_skipped() -> None:
    assert write_pending(Decision(action=Action.SKIPPED)) is None


def test_review() -> None:
    d = Decision(
        doc=DocRef(url="https://feishu.cn/docx/r", source_chat="T", source_chat_id="x"),
        judgment=RouteJudgment(doc_type_name="PRD", should_process=True, reason="m"),
        action=Action.APPROVED,
    )
    p = write_pending(d)
    assert review("accepted", p.name)
    assert "status: accepted" in p.read_text()


def test_decision_to_dict() -> None:
    dc = Decision(doc=DocRef(url="https://x.com/doc", source_chat="T"),
                  action=Action.APPROVED).to_dict()
    assert dc["action"] == "approved" and dc["doc"]["url"] == "https://x.com/doc"
