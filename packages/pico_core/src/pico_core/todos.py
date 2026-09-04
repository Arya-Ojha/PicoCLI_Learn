"""Agent work-tracking: a todo list the model maintains via the ``todo_write`` tool.

Semantics mirror the classic plan-then-execute loop: the agent writes the full
list up front, keeps exactly one item ``in_progress`` while work remains, and
marks items ``completed`` as it finishes them. State is session-scoped and
in-memory — it is working memory, not persisted history.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .tools import ToolOutcome

TodoStatus = Literal["pending", "in_progress", "completed"]
TodoPriority = Literal["high", "medium", "low"]

_STATUS_MARKS = {
    "completed": "[x]",
    "in_progress": "[>]",
    "pending": "[ ]",
}


class TodoItem(BaseModel):
    """A single tracked work item."""

    content: str
    status: TodoStatus = "pending"
    priority: TodoPriority = "medium"


class TodoStore:
    """Holds the session's todo list and enforces its invariants."""

    def __init__(self) -> None:
        self._items: list[TodoItem] = []

    @property
    def items(self) -> list[TodoItem]:
        return list(self._items)

    def replace(self, items: list[TodoItem]) -> list[TodoItem]:
        """Replace the whole list, enforcing exactly-one-in-progress.

        When several items arrive ``in_progress``, the first keeps it and the
        rest fall back to ``pending`` so the list always has a single focus.
        """
        seen_focus = False
        normalized: list[TodoItem] = []
        for item in items:
            if item.status == "in_progress":
                if seen_focus:
                    normalized.append(item.model_copy(update={"status": "pending"}))
                else:
                    seen_focus = True
                    normalized.append(item)
            else:
                normalized.append(item)
        self._items = normalized
        return self.items


def format_todos(items: list[TodoItem]) -> str:
    """Render the list as a compact plain-text checklist (ASCII only)."""
    if not items:
        return "todo list is empty"
    return "\n".join(
        f"{_STATUS_MARKS[item.status]} {item.content}" for item in items
    )


_TODO_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "completed"],
        },
        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["content", "status"],
}


class TodoWriteTool:
    """Replace the session todo list (session-scoped working memory)."""

    name = "todo_write"
    description = (
        "Track multi-step work. Pass the FULL list every time: plan all steps "
        "up front for tasks with 3+ steps, keep exactly one item in_progress "
        "while work remains, and mark items completed as you finish them."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "todos": {"type": "array", "items": _TODO_ITEM_SCHEMA},
        },
        "required": ["todos"],
    }

    def __init__(self, store: TodoStore) -> None:
        self._store = store

    async def run(self, arguments: dict) -> ToolOutcome:
        raw = arguments.get("todos")
        if not isinstance(raw, list):
            return ToolOutcome(content="error: 'todos' must be a list", is_error=True)
        items: list[TodoItem] = []
        for entry in raw:
            if not isinstance(entry, dict) or not str(entry.get("content", "")).strip():
                return ToolOutcome(
                    content="error: every todo needs a non-empty 'content'",
                    is_error=True,
                )
            status = entry.get("status", "pending")
            if status not in _STATUS_MARKS:
                return ToolOutcome(
                    content=f"error: bad status {status!r}; use pending, "
                    "in_progress, or completed",
                    is_error=True,
                )
            priority = entry.get("priority", "medium")
            if priority not in ("high", "medium", "low"):
                return ToolOutcome(
                    content=f"error: bad priority {priority!r}; use high, "
                    "medium, or low",
                    is_error=True,
                )
            items.append(
                TodoItem(
                    content=str(entry["content"]).strip(),
                    status=status,  # type: ignore[arg-type]
                    priority=priority,  # type: ignore[arg-type]
                )
            )
        current = self._store.replace(items)
        return ToolOutcome(content=format_todos(current))
