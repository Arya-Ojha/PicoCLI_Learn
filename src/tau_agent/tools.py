from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from .types import JSONObject, JSONValue


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


ToolResultStatus = Literal["ok", "error"]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str | None = None
    input_schema: JSONObject | None = None

    def to_dict(self) -> JSONObject:
        out: JSONObject = {"name": self.name}
        if self.description is not None:
            out["description"] = self.description
        if self.input_schema is not None:
            out["input_schema"] = self.input_schema
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "ToolDefinition":
        return cls(
            name=str(data["name"]),
            description=data.get("description") if isinstance(data.get("description"), str) else None,
            input_schema=data.get("input_schema") if isinstance(data.get("input_schema"), dict) else None,
        )


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: JSONObject = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> JSONObject:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: JSONObject) -> "ToolCall":
        created_at_raw = data.get("created_at")
        created_at = utc_now()
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except ValueError:
                created_at = utc_now()

        return cls(
            id=str(data["id"]) if "id" in data else uuid4().hex,
            name=str(data["name"]),
            arguments=data.get("arguments") if isinstance(data.get("arguments"), dict) else {},
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_call_id: str
    name: str
    status: ToolResultStatus = "ok"
    content: JSONValue | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }
        if self.content is not None:
            out["content"] = self.content
        if self.error is not None:
            out["error"] = self.error
        return out

    @classmethod
    def from_dict(cls, data: JSONObject) -> "ToolResult":
        created_at_raw = data.get("created_at")
        created_at = utc_now()
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except ValueError:
                created_at = utc_now()

        status_raw = data.get("status")
        status: ToolResultStatus = "ok" if status_raw != "error" else "error"

        error = data.get("error") if isinstance(data.get("error"), str) else None
        content = data.get("content") if "content" in data else None

        return cls(
            tool_call_id=str(data["tool_call_id"]),
            name=str(data["name"]),
            status=status,
            content=content,
            error=error,
            created_at=created_at,
        )
