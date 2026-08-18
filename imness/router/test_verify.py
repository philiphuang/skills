"""verify 模块单元测试。"""
from pathlib import Path

from .verify import (
    verify_messages, verify_doc_ref, verify_ai_response,
    verify_pending_file, verify_config, verify_pending_batch,
)
from .route import PENDING_DIR, write_pending
from .decision import Decision, DocRef, DocType, RouteJudgment, Action


# === 消息验证 ===

def test_verify_messages_valid() -> None:
    assert verify_messages([
        {"chat_name": "T", "chat_id": "x", "content": "hi"}
    ]) == []


def test_verify_messages_missing() -> None:
    issues = verify_messages([{"chat_name": "T", "chat_id": "x"}])
    assert any("content" in i for i in issues)


def test_verify_messages_not_list() -> None:
    assert verify_messages({}) == ["消息输入必须是列表"]


# === 文档引用验证 ===

def test_verify_doc_ref_valid() -> None:
    assert verify_doc_ref({"url": "https://x.com", "source_chat": "T"}) == []


def test_verify_doc_ref_empty() -> None:
    issues = verify_doc_ref({})
    assert len(issues) == 2


# === AI 响应验证 ===

def test_verify_ai_valid() -> None:
    assert verify_ai_response({
        "doc_type": "PRD", "should_process": True, "reason": "ok"
    }) == []


def test_verify_ai_missing() -> None:
    issues = verify_ai_response({})
    assert len(issues) == 3


def test_verify_ai_wrong_type() -> None:
    issues = verify_ai_response({
        "doc_type": "PRD", "should_process": "yes", "reason": "ok"
    })
    assert any("should_process" in i for i in issues)


# === 待审文件验证 ===

def test_verify_pending_valid() -> None:
    d = Decision(
        doc=DocRef(url="https://feishu.cn/docx/t", doc_type=DocType.ONLINE,
                   source_chat="T", source_chat_id="x"),
        judgment=RouteJudgment(doc_type_name="PRD", should_process=True, reason="m"),
        action=Action.APPROVED,
    )
    p = write_pending(d)
    assert verify_pending_file(p) == []


def test_verify_pending_missing() -> None:
    assert "不存在" in verify_pending_file(Path("/no/such/file"))[0]


# === 配置验证 ===

def test_verify_config() -> None:
    assert verify_config() == []


# === 批量待审池 ===

def test_verify_pending_batch() -> None:
    valid, _ = verify_pending_batch()
    # 可能有之前测试遗留的文件，至少不报错
    assert isinstance(valid, list)
