"""Tickets 02/03/04 — AgentSession: tracer bullet, tools, fork, persistence."""

from pico_ai.types import StreamEvent, ToolCall
from pico_core.session import (
    AssistantPayload,
    Session,
    ToolRequestPayload,
    ToolResultPayload,
    UserPayload,
)
from pico_sdk.session import AgentSession

from conftest import FakeProvider, make_session


async def test_tracer_bullet_run(tmp_path):
    provider = FakeProvider([[StreamEvent(kind="text", text="Hello")]])
    session = make_session(provider, tmp_path)
    result = await session.run("hello")
    assert result.text == "Hello"
    branch = session.session.active_branch()
    assert [type(n.payload) for n in branch] == [UserPayload, AssistantPayload]


async def test_save_persists_jsonl(tmp_path):
    provider = FakeProvider([[StreamEvent(kind="text", text="Hello")]])
    session = make_session(provider, tmp_path)
    await session.run("hello")
    path = session.save()
    assert path.exists()
    loaded = Session.load(path)
    assert [type(n.payload) for n in loaded.active_branch()] == [
        UserPayload,
        AssistantPayload,
    ]


async def test_resume_from_disk(tmp_path):
    provider = FakeProvider(
        [
            [StreamEvent(kind="text", text="first")],
            [StreamEvent(kind="text", text="second")],
        ]
    )
    session = make_session(provider, tmp_path)
    await session.run("one")
    session.save()

    resumed = AgentSession.load(
        session.session.id,
        provider=provider,
        settings=session.settings,
        working_dir=tmp_path,
    )
    assert resumed.session.id == session.session.id
    assert len(resumed.session.nodes) == len(session.session.nodes)
    await resumed.run("two")
    kinds = [type(n.payload) for n in resumed.session.active_branch()]
    assert kinds.count(UserPayload) == 2


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


async def test_fork_via_agent_session(tmp_path):
    provider = FakeProvider(
        [
            [StreamEvent(kind="text", text="first")],
            [StreamEvent(kind="text", text="second")],
        ]
    )
    session = make_session(provider, tmp_path)
    await session.run("one")
    fork_point = session.session.active_leaf_id
    await session.run("two")
    session.fork(fork_point)
    assert session.session.active_leaf_id == fork_point

