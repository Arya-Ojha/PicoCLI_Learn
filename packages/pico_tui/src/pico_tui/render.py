"""Rich-based event renderer for LoopEvent → Rich renderable."""

from __future__ import annotations

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from pico_sdk import LoopEvent

# Distinct heading colors per tool type.
_TOOL_COLORS: dict[str, str] = {
    "bash": "green",
    "read": "bright_blue",
    "write": "yellow",
    "edit": "magenta",
    "lesson": "red",
    "fetch": "cyan",
    "search": "blue",
}


def _truncate(text: str, limit: int = 200) -> str:
    """Collapse whitespace and truncate long tool output."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


def render_event(event: LoopEvent):  # -> RenderableType (kept loose for mypy simplicity)
    """Convert a LoopEvent to a Rich renderable for display in a RichLog.

    Returns None when the event should produce no visible output.
    """
    if event.kind == "text":
        return (
            Markdown(event.text)
            if _looks_like_markdown(event.text)
            else Text(event.text)
        )
    if event.kind == "thinking":
        return Text(event.thinking, style="dim italic")
    if event.kind == "tool_request" and event.tool_request is not None:
        call = event.tool_request.tool_call
        color = _TOOL_COLORS.get(call.name, "cyan")
        if call.name == "bash":
            cmd = call.arguments.get("command", "")
            return Panel(
                cmd,
                title=f"[bold {color}]{call.name}[/]",
                border_style=color,
                title_align="left",
            )
        return Panel(
            str(call.arguments),
            title=f"[bold {color}]{call.name}[/]",
            border_style=color,
            title_align="left",
        )
    if event.kind == "tool_result" and event.tool_result is not None:
        result = event.tool_result
        color = _TOOL_COLORS.get(result.name, "dim cyan")
        if result.name == "bash":
            return Panel(
                result.content.rstrip(),
                title=f"[{color}]{result.name} result[/]",
                border_style=color,
                title_align="left",
            )
        snippet = _truncate(result.content)
        return Panel(
            snippet,
            title=f"[{color}]{result.name} result[/]",
            border_style=color,
            title_align="left",
        )
    if event.kind == "usage" and event.usage is not None:
        u = event.usage
        return Text(f"({u.input_tokens}↓ {u.output_tokens}↑)", style="dim")
    return None


def _looks_like_markdown(text: str) -> bool:
    """Heuristic: use Rich Markdown for multi-line or formatted responses."""
    return "\n" in text or any(
        marker in text for marker in ("```", "**", "# ", "- ", "1. ", "|")
    )
