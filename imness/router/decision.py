"""文档路由决策数据模型。"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Action(str, Enum):
    APPROVED = "approved"
    SKIPPED = "skipped"


class DocType(str, Enum):
    ONLINE = "online"
    ATTACHMENT = "attachment"


@dataclass
class DocRef:
    url: str = ""
    filename: str = ""
    doc_type: DocType = DocType.ONLINE
    source_chat: str = ""
    source_chat_id: str = ""
    context_snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url, "filename": self.filename,
            "doc_type": self.doc_type.value,
            "source_chat": self.source_chat, "source_chat_id": self.source_chat_id,
            "context_snippet": self.context_snippet,
        }


@dataclass
class RouteJudgment:
    doc_type_name: str = ""
    should_process: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "doc_type_name": self.doc_type_name,
            "should_process": self.should_process,
            "reason": self.reason,
        }


@dataclass
class Decision:
    doc: Optional[DocRef] = None
    judgment: RouteJudgment = field(default_factory=RouteJudgment)
    action: Action = Action.SKIPPED
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "doc": self.doc.to_dict() if self.doc else {},
            "judgment": self.judgment.to_dict(),
            "action": self.action.value,
            "summary": self.summary,
        }
