"""Smoke: TUI command parsing + text rendering."""

from rich.console import Console

from pico_core.fsm import LoopEvent
from pico_tui.commands import Command, parse_line
from pico_tui.render import render_event

_console = Console(force_terminal=True, color_system=None, width=200, height=100)


def _render_text(event: LoopEvent) -> str:
    rendered = render_event(event)
    if rendered is None:
        return ""
    with _console.capture() as capture:
        _console.print(rendered)
    return capture.get().rstrip()


def test_parse_line_commands():
    assert parse_line("/quit") == Command("quit")
    assert parse_line("/help") == Command("help")
    assert parse_line("/history") == Command("history")
    assert parse_line("/undo") == Command("undo")
    assert parse_line("/compact focus on the bug") == Command("compact", "focus on the bug")
    assert parse_line("/fork abc123") == Command("fork", "abc123")


def test_render_event_text():
    event = LoopEvent(kind="text", text="hi")
    assert _render_text(event) == "hi"
