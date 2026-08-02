from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias
from uuid import uuid4

from .tools import ToolCall, utc_now
from .types import JSONObject, JSONValue


MessageRole: TypeAlias = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class SystemMessage:
    content: str
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)
    metadata: JSONObject | None = None

    @property
    def role(self) -> MessageRole:
        return "system"

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }
        if self.metadata is not None:
            out["metadata"] = self.metadata
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "SystemMessage":
        created_at_raw = data.get("created_at")
        created_at = utc_now()
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except ValueError:
                created_at = utc_now()

        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            content=str(data.get("content") or ""),
            created_at=created_at,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )


@dataclass(frozen=True, slots=True)
class UserMessage:
    content: str
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)
    metadata: JSONObject | None = None

    @property
    def role(self) -> MessageRole:
        return "user"

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }
        if self.metadata is not None:
            out["metadata"] = self.metadata
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "UserMessage":
        created_at_raw = data.get("created_at")
        created_at = utc_now()
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except ValueError:
                created_at = utc_now()

        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            content=str(data.get("content") or ""),
            created_at=created_at,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)
    metadata: JSONObject | None = None

    @property
    def role(self) -> MessageRole:
        return "assistant"

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "id": self.id,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }
        if self.content is not None:
            out["content"] = self.content
        if self.tool_calls:
            out["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.metadata is not None:
            out["metadata"] = self.metadata
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "AssistantMessage":
        created_at_raw = data.get("created_at")
        created_at = utc_now()
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except ValueError:
                created_at = utc_now()

        tool_calls: list[ToolCall] = []
        tool_calls_raw = data.get("tool_calls")
        if isinstance(tool_calls_raw, list):
            for item in tool_calls_raw:
                if isinstance(item, dict):
                    tool_calls.append(ToolCall.from_dict(item))

        content_raw = data.get("content")
        content = content_raw if isinstance(content_raw, str) else None

        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            content=content,
            tool_calls=tool_calls,
            created_at=created_at,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )


@dataclass(frozen=True, slots=True)
class ToolMessage:
    tool_call_id: str
    name: str
    content: JSONValue | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)
    metadata: JSONObject | None = None

    @property
    def role(self) -> MessageRole:
        return "tool"

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "id": self.id,
            "role": self.role,
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
        }
        if self.content is not None:
            out["content"] = self.content
        if self.metadata is not None:
            out["metadata"] = self.metadata
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "ToolMessage":
        created_at_raw = data.get("created_at")
        created_at = utc_now()
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except ValueError:
                created_at = utc_now()

        content = data.get("content") if "content" in data else None

        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            tool_call_id=str(data.get("tool_call_id") or ""),
            name=str(data.get("name") or ""),
            content=content,
            created_at=created_at,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )


TranscriptMessage: TypeAlias = SystemMessage | UserMessage | AssistantMessage | ToolMessage


def message_from_dict(data: JSONObject) -> TranscriptMessage:
    role = data.get("role")
    if role == "system":
        return SystemMessage.from_dict(data)
    if role == "user":
        return UserMessage.from_dict(data)
    if role == "assistant":
        return AssistantMessage.from_dict(data)
    if role == "tool":
        return ToolMessage.from_dict(data)
    return UserMessage.from_dict(data)
