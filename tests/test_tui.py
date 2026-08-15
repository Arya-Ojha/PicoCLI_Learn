"""The pico_tui terminal UI: command parsing, event rendering, and the REPL."""

from pico_ai.types import StreamEvent, ToolCall
from pico_core.fsm import LoopEvent
from pico_core.session import ToolRequestPayload, ToolResultPayload
from pico_tui.app import TUI, Command, Prompt, parse_line, render_event

from conftest import FakeProvider, make_session


def test_parse_line_commands():
    assert parse_line("/quit") == Command("quit")
    assert parse_line("/exit") == Command("quit")
    assert parse_line("/help") == Command("help")
    assert parse_line("/compact focus on the bug") == Command("compact", "focus on the bug")
    assert parse_line("/fork abc123") == Command("fork", "abc123")


def test_parse_line_prompt():
    assert parse_line("hello world") == Prompt("hello world")
    assert parse_line("  hi  ") == Prompt("hi")


def test_render_event_text():
    assert render_event(LoopEvent(kind="text", text="hi")) == "hi"


def test_render_event_thinking_is_hidden():
    assert render_event(LoopEvent(kind="thinking", thinking="hmm")) == ""


def test_render_event_bash_request_echoes():
    event = LoopEvent(
        kind="tool_request",
        tool_request=ToolRequestPayload(
            tool_call=ToolCall(id="c1", name="bash", arguments={"command": "ls"})
        ),
    )
    assert render_event(event) == "$ ls\n"


def test_render_event_other_tool_request():
    event = LoopEvent(
        kind="tool_request",
        tool_request=ToolRequestPayload(
            tool_call=ToolCall(id="c1", name="read", arguments={"path": "a.txt"})
        ),
    )
    assert render_event(event) == "[read] {'path': 'a.txt'}\n"


def test_render_event_bash_result():
    event = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c1", name="bash", content="hi\n[exit code: 0]"
        ),
    )
    assert render_event(event) == "hi\n[exit code: 0]\n"


def test_render_event_non_bash_result_hidden():
    event = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(tool_call_id="c1", name="read", content="data"),
    )
    assert render_event(event) == ""


async def test_tui_runs_prompt_and_quits(tmp_path):
    provider = FakeProvider([[StreamEvent(kind="text", text="Hello")]])
    session = make_session(provider, tmp_path)
    lines = iter(["hello", "/quit"])
    output: list[str] = []

    tui = TUI(session, input_fn=lambda prompt="": next(lines), write=output.append)
    await tui.run()
    assert "Hello" in "".join(output)
