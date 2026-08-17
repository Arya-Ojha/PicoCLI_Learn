"""pico_tui tests: command parsing, Rich rendering, and Textual pilot."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from pico_ai.types import StreamEvent, ToolCall, Usage
from pico_core.fsm import LoopEvent
from pico_core.session import ToolRequestPayload, ToolResultPayload

from pico_tui.commands import Command, Prompt, parse_line
from pico_tui.render import render_event

# Shared console for rendering-to-text assertions.
_console = Console(force_terminal=True, color_system=None, width=200, height=100)


def _render_text(event: LoopEvent) -> str:
    """Render a LoopEvent to plain text for assertion."""
    rendered = render_event(event)
    if rendered is None:
        return ""
    with _console.capture() as capture:
        _console.print(rendered)
    return capture.get().rstrip()


# ── parse_line ──────────────────────────────────────────────────────


def test_parse_line_commands():
    assert parse_line("/quit") == Command("quit")
    assert parse_line("/exit") == Command("quit")
    assert parse_line("/help") == Command("help")
    assert parse_line("/history") == Command("history")
    assert parse_line("/undo") == Command("undo")
    assert parse_line("/compact focus on the bug") == Command("compact", "focus on the bug")
    assert parse_line("/fork abc123") == Command("fork", "abc123")


def test_parse_line_prompt():
    assert parse_line("hello world") == Prompt("hello world")
    assert parse_line("  hi  ") == Prompt("hi")


def test_parse_line_empty():
    assert parse_line("") == Prompt("")
    assert parse_line("   ") == Prompt("")


# ── render_event ────────────────────────────────────────────────────


def test_render_event_text():
    event = LoopEvent(kind="text", text="hi")
    assert _render_text(event) == "hi"


def test_render_event_markdown():
    event = LoopEvent(kind="text", text="# Title\n\n- item 1\n- item 2")
    result = _render_text(event)
    assert "Title" in result
    assert "item 1" in result


def test_render_event_thinking():
    event = LoopEvent(kind="thinking", thinking="hmm let me think")
    assert "hmm let me think" in _render_text(event)


def test_render_event_bash_request():
    event = LoopEvent(
        kind="tool_request",
        tool_request=ToolRequestPayload(
            tool_call=ToolCall(id="c1", name="bash", arguments={"command": "ls -la"})
        ),
    )
    result = _render_text(event)
    assert "ls -la" in result
    assert "bash" in result.lower()


def test_render_event_read_request():
    event = LoopEvent(
        kind="tool_request",
        tool_request=ToolRequestPayload(
            tool_call=ToolCall(id="c1", name="read", arguments={"path": "a.txt"})
        ),
    )
    result = _render_text(event)
    assert "read" in result
    assert "a.txt" in result


def test_render_event_bash_result():
    event = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c1", name="bash", content="file1.txt\n[exit code: 0]"
        ),
    )
    result = _render_text(event)
    assert "file1.txt" in result


def test_render_event_read_result():
    event = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c1", name="read", content="hello world from file"
        ),
    )
    result = _render_text(event)
    assert "hello world from file" in result


def test_render_event_usage():
    event = LoopEvent(kind="usage", usage=Usage(input_tokens=10, output_tokens=5))
    result = _render_text(event)
    assert "10" in result
    assert "5" in result


def test_render_event_returns_rich_renderable():
    """render_event returns Rich objects, not raw strings."""
    event = LoopEvent(kind="text", text="# Title")
    rendered = render_event(event)
    # Rich Markdown objects are not plain strings
    assert not isinstance(rendered, str)

    event2 = LoopEvent(kind="thinking", thinking="hmm")
    rendered2 = render_event(event2)
    assert isinstance(rendered2, Text)

    event3 = LoopEvent(
        kind="tool_request",
        tool_request=ToolRequestPayload(
            tool_call=ToolCall(id="c1", name="bash", arguments={"command": "ls"})
        ),
    )
    rendered3 = render_event(event3)
    assert isinstance(rendered3, Panel)

