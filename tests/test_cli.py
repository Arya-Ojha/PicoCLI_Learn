"""The ``pico`` CLI's event rendering."""

from pico_ai.types import ToolCall
from pico_core.fsm import LoopEvent
from pico_core.session import ToolRequestPayload, ToolResultPayload
from pico_sdk.cli import format_event


def test_format_event_prints_text():
    assert format_event(LoopEvent(kind="text", text="hello")) == "hello"


def test_format_event_echoes_bash_before_execution():
    request = LoopEvent(
        kind="tool_request",
        tool_request=ToolRequestPayload(
            tool_call=ToolCall(id="c1", name="bash", arguments={"command": "echo hi"})
        ),
    )
    assert format_event(request) == "$ echo hi\n"


def test_format_event_prints_bash_result():
    result = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c1", name="bash", content="hi\n[exit code: 0]"
        ),
    )
    assert format_event(result) == "hi\n[exit code: 0]\n"


def test_format_event_ignores_non_bash_tools():
    result = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(tool_call_id="c1", name="read", content="data"),
    )
    assert format_event(result) is None
