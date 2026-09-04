"""Smoke: FSM tracer bullet + tool loop."""

from pico_ai.types import StreamEvent, ToolCall
from pico_core.fsm import AgentLoop, AgentState
from pico_core.session import (
    AssistantPayload,
    Session,
    ToolRequestPayload,
    ToolResultPayload,
    UserPayload,
)
from pico_core.tools import ReadTool, ToolRegistry

from conftest import FakeProvider


def _registry(cwd):
    reg = ToolRegistry()
    reg.register(ReadTool(cwd))
    return reg


async def test_tracer_bullet_text_response():
    provider = FakeProvider([[StreamEvent(kind="text", text="Hello")]])
    session = Session()
    loop = AgentLoop(provider, session, ToolRegistry())
    result = await loop.run("hello")
    assert result.text == "Hello"
    assert result.state == AgentState.DONE
    branch = session.active_branch()
    assert [type(n.payload) for n in branch] == [UserPayload, AssistantPayload]


async def test_tool_loop_and_result_feedback(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    provider = FakeProvider(
        [
            [StreamEvent(kind="tool_call", tool_call=ToolCall(id="c1", name="read", arguments={"path": "a.txt"}))],
            [StreamEvent(kind="text", text="done")],
        ]
    )
    session = Session()
    loop = AgentLoop(provider, session, _registry(tmp_path))
    result = await loop.run("read a.txt")
    assert result.text == "done"
    assert result.state == AgentState.DONE
    kinds = [type(n.payload) for n in session.active_branch()]
    assert kinds == [
        UserPayload,
        AssistantPayload,
        ToolRequestPayload,
        ToolResultPayload,
        AssistantPayload,
    ]
