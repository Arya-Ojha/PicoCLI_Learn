from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias
from uuid import uuid4

from .messages import TranscriptMessage, message_from_dict
from .tools import ToolCall, ToolResult, utc_now
from .types import JSONObject


EventType: TypeAlias = Literal[
    "agent_started",
    "agent_finished",
    "message",
    "tool_call",
    "tool_result",
    "error",
]


def parse_datetime(value: object) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return utc_now()
    return utc_now()


@dataclass(frozen=True, slots=True)
class AgentStartedEvent:
    run_id: str
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)
    metadata: JSONObject | None = None

    @property
    def type(self) -> EventType:
        return "agent_started"

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "id": self.id,
            "type": self.type,
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
        }
        if self.metadata is not None:
            out["metadata"] = self.metadata
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "AgentStartedEvent":
        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            run_id=str(data.get("run_id") or ""),
            created_at=parse_datetime(data.get("created_at")),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )


@dataclass(frozen=True, slots=True)
class AgentFinishedEvent:
    run_id: str
    status: Literal["ok", "error"] = "ok"
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)
    metadata: JSONObject | None = None

    @property
    def type(self) -> EventType:
        return "agent_finished"

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "id": self.id,
            "type": self.type,
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }
        if self.metadata is not None:
            out["metadata"] = self.metadata
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "AgentFinishedEvent":
        status_raw = data.get("status")
        status: Literal["ok", "error"] = "error" if status_raw == "error" else "ok"
        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            run_id=str(data.get("run_id") or ""),
            status=status,
            created_at=parse_datetime(data.get("created_at")),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )


@dataclass(frozen=True, slots=True)
class MessageEvent:
    message: TranscriptMessage
    run_id: str | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)

    @property
    def type(self) -> EventType:
        return "message"

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "id": self.id,
            "type": self.type,
            "message": self.message.to_dict(),
            "created_at": self.created_at.isoformat(),
        }
        if self.run_id is not None:
            out["run_id"] = self.run_id
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "MessageEvent":
        msg_raw = data.get("message")
        msg: TranscriptMessage
        if isinstance(msg_raw, dict):
            msg = message_from_dict(msg_raw)
        else:
            msg = message_from_dict({"role": "user", "content": ""})

        run_id_raw = data.get("run_id")
        run_id = run_id_raw if isinstance(run_id_raw, str) else None

        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            message=msg,
            run_id=run_id,
            created_at=parse_datetime(data.get("created_at")),
        )


@dataclass(frozen=True, slots=True)
class ToolCallEvent:
    tool_call: ToolCall
    run_id: str | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)

    @property
    def type(self) -> EventType:
        return "tool_call"

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "id": self.id,
            "type": self.type,
            "tool_call": self.tool_call.to_dict(),
            "created_at": self.created_at.isoformat(),
        }
        if self.run_id is not None:
            out["run_id"] = self.run_id
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "ToolCallEvent":
        call_raw = data.get("tool_call")
        call = ToolCall.from_dict(call_raw) if isinstance(call_raw, dict) else ToolCall(name="")

        run_id_raw = data.get("run_id")
        run_id = run_id_raw if isinstance(run_id_raw, str) else None

        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            tool_call=call,
            run_id=run_id,
            created_at=parse_datetime(data.get("created_at")),
        )


@dataclass(frozen=True, slots=True)
class ToolResultEvent:
    tool_result: ToolResult
    run_id: str | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)

    @property
    def type(self) -> EventType:
        return "tool_result"

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "id": self.id,
            "type": self.type,
            "tool_result": self.tool_result.to_dict(),
            "created_at": self.created_at.isoformat(),
        }
        if self.run_id is not None:
            out["run_id"] = self.run_id
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "ToolResultEvent":
        result_raw = data.get("tool_result")
        result = (
            ToolResult.from_dict(result_raw) if isinstance(result_raw, dict) else ToolResult(tool_call_id="", name="")
        )

        run_id_raw = data.get("run_id")
        run_id = run_id_raw if isinstance(run_id_raw, str) else None

        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            tool_result=result,
            run_id=run_id,
            created_at=parse_datetime(data.get("created_at")),
        )


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    message: str
    run_id: str | None = None
    details: JSONObject | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)

    @property
    def type(self) -> EventType:
        return "error"

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "id": self.id,
            "type": self.type,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
        }
        if self.run_id is not None:
            out["run_id"] = self.run_id
        if self.details is not None:
            out["details"] = self.details
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "ErrorEvent":
        details = data.get("details") if isinstance(data.get("details"), dict) else None

        run_id_raw = data.get("run_id")
        run_id = run_id_raw if isinstance(run_id_raw, str) else None

        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            message=str(data.get("message") or ""),
            run_id=run_id,
            details=details,
            created_at=parse_datetime(data.get("created_at")),
        )


AgentEvent: TypeAlias = (
    AgentStartedEvent | AgentFinishedEvent | MessageEvent | ToolCallEvent | ToolResultEvent | ErrorEvent
)


def event_from_dict(data: JSONObject) -> AgentEvent:
    typ = data.get("type")
    if typ == "agent_started":
        return AgentStartedEvent.from_dict(data)
    if typ == "agent_finished":
        return AgentFinishedEvent.from_dict(data)
    if typ == "message":
        return MessageEvent.from_dict(data)
    if typ == "tool_call":
        return ToolCallEvent.from_dict(data)
    if typ == "tool_result":
        return ToolResultEvent.from_dict(data)
    if typ == "error":
        return ErrorEvent.from_dict(data)
    return ErrorEvent.from_dict({"message": "unknown event type"})
