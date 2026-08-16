"""The pico_tui terminal UI: command parsing, event rendering, and the REPL."""

from pico_ai.types import StreamEvent, ToolCall, Usage
from pico_core.fsm import LoopEvent
from pico_core.session import ToolRequestPayload, ToolResultPayload
from pico_tui.app import TUI, Command, Prompt, parse_line, render_event

from conftest import FakeProvider, make_session


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


def test_render_event_text():
    assert render_event(LoopEvent(kind="text", text="hi")) == "hi"


def test_render_event_thinking():
    assert render_event(LoopEvent(kind="thinking", thinking="hmm")) == "hmm"


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


def test_render_event_non_bash_result():
    event = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(tool_call_id="c1", name="read", content="data"),
    )
    assert render_event(event) == "  -> data\n"


def test_render_event_usage():
    event = LoopEvent(kind="usage", usage=Usage(input_tokens=10, output_tokens=5))
    assert render_event(event) == "  (10 in, 5 out)\n"


def test_render_event_color_wraps_ansi():
    event = LoopEvent(
        kind="tool_request",
        tool_request=ToolRequestPayload(
            tool_call=ToolCall(id="c1", name="bash", arguments={"command": "ls"})
        ),
    )
    assert render_event(event, color=True) == "\033[32m$ ls\n\033[0m"


async def test_tui_runs_prompt_and_quits(tmp_path):
    provider = FakeProvider([[StreamEvent(kind="text", text="Hello")]])
    session = make_session(provider, tmp_path)
    lines = iter(["hello", "/quit"])
    output: list[str] = []

    tui = TUI(session, input_fn=lambda prompt="": next(lines), write=output.append)
    await tui.run()
    assert "Hello" in "".join(output)


async def test_tui_history_and_undo(tmp_path):
    provider = FakeProvider(
        [
            [StreamEvent(kind="text", text="first")],
            [StreamEvent(kind="text", text="second")],
        ]
    )
    session = make_session(provider, tmp_path)
    lines = iter(["one", "two", "/history", "/undo", "/quit"])
    output: list[str] = []

    tui = TUI(session, input_fn=lambda prompt="": next(lines), write=output.append)
    await tui.run()
    joined = "".join(output)
    assert "first" in joined
    assert "second" in joined
    assert "[0] user" in joined  # /history lists nodes
    assert "rewound" in joined  # /undo ran

