"""Smoke: AgentSession tracer bullet + tool loop."""

from pico_ai.types import StreamEvent, ToolCall
from pico_core.session import (
    AssistantPayload,
    ToolRequestPayload,
    ToolResultPayload,
    UserPayload,
)

from conftest import FakeProvider, make_session


async def test_tracer_bullet_run(tmp_path):
    provider = FakeProvider([[StreamEvent(kind="text", text="Hello")]])
    session = make_session(provider, tmp_path)
    result = await session.run("hello")
    assert result.text == "Hello"
    branch = session.session.active_branch()
    assert [type(n.payload) for n in branch] == [UserPayload, AssistantPayload]


async def test_tool_loop_via_agent_session(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    provider = FakeProvider(
        [
            [StreamEvent(kind="tool_call", tool_call=ToolCall(id="c1", name="read", arguments={"path": "a.txt"}))],
            [StreamEvent(kind="text", text="done")],
        ]
    )
    session = make_session(provider, tmp_path)
    result = await session.run("read a.txt")
    assert result.text == "done"
    kinds = [type(n.payload) for n in session.session.active_branch()]
    assert kinds == [
        UserPayload,
        AssistantPayload,
        ToolRequestPayload,
        ToolResultPayload,
        AssistantPayload,
    ]
