"""Smoke: CLI event rendering + default flags."""

from pico_core.fsm import LoopEvent
from pico_sdk.cli import build_parser, format_event


def test_format_event_prints_text():
    assert format_event(LoopEvent(kind="text", text="hello")) == "hello"


def test_bash_enabled_by_default():
    args = build_parser().parse_args(["run", "hi"])
    assert args.no_bash is False


def test_bash_result_hides_output():
    from pico_core.session import ToolResultPayload

    ok = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c1", name="bash", content="secret output\n[exit code: 0]"
        ),
    )
    rendered = format_event(ok)
    assert rendered is not None
    assert "secret output" not in rendered
    assert "passed" in rendered

    err = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c2", name="bash", content="boom\n[exit code: 1]", is_error=True
        ),
    )
    assert "error" in (format_event(err) or "")
