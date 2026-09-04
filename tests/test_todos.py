"""Smoke: todo store invariant + todo_write tool + CLI rendering."""

from pico_core.fsm import LoopEvent
from pico_core.session import ToolResultPayload
from pico_core.todos import TodoItem, TodoStore, TodoWriteTool
from pico_sdk.cli import format_event


async def test_todo_write_keeps_single_focus():
    store = TodoStore()
    tool = TodoWriteTool(store)
    outcome = await tool.run(
        {
            "todos": [
                {"content": "plan", "status": "completed"},
                {"content": "build", "status": "in_progress"},
                {"content": "verify", "status": "in_progress"},
            ]
        }
    )
    assert not outcome.is_error
    assert "[x] plan" in outcome.content
    assert "[>] build" in outcome.content
    # Second in_progress falls back to pending.
    assert "[ ] verify" in outcome.content
    assert store.items[2].status == "pending"


async def test_todo_write_rejects_bad_input():
    tool = TodoWriteTool(TodoStore())
    empty = await tool.run({"todos": [{"content": "  ", "status": "pending"}]})
    assert empty.is_error
    assert "non-empty" in empty.content
    bad = await tool.run({"todos": [{"content": "x", "status": "done"}]})
    assert bad.is_error
    assert "bad status" in bad.content


def test_todo_result_prints_checklist_in_cli():
    event = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c1",
            name="todo_write",
            content="[x] plan\n[>] build",
        ),
    )
    rendered = format_event(event)
    assert rendered is not None
    assert rendered.startswith("# Todos\n")
    assert "todo_write" not in rendered
    assert "[x] plan" in rendered
    # Active item is colored green (no panel/border chrome).
    assert "\x1b[32m[>] build\x1b[0m" in rendered


def test_session_registers_todo_tool(tmp_path):
    from conftest import FakeProvider, make_session

    session = make_session(FakeProvider([]), tmp_path)
    assert "todo_write" in session.tools.names()
    assert isinstance(session.todos, TodoStore)
    assert isinstance(session.tools.get("todo_write"), TodoWriteTool)
