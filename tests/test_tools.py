"""Smoke: core tools read + bash (cwd-jail)."""

from pico_core.tools import BashTool, ReadTool, WriteTool


async def test_read_existing_file(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    outcome = await ReadTool(tmp_path).run({"path": "a.txt"})
    assert outcome.content == "hello"
    assert not outcome.is_error


async def test_bash_runs_and_captures_output(tmp_path):
    outcome = await BashTool(tmp_path, enabled=True).run({"command": "echo hi"})
    assert not outcome.is_error
    assert "hi" in outcome.content
    assert "[exit code: 0]" in outcome.content


async def test_read_rejects_absolute_escape(tmp_path):
    outcome = await ReadTool(tmp_path).run({"path": "/etc/passwd"})
    assert outcome.is_error
    assert "cwd-jail" in outcome.content


async def test_read_rejects_dotdot_escape(tmp_path):
    outcome = await ReadTool(tmp_path).run({"path": "../outside.txt"})
    assert outcome.is_error
    assert "cwd-jail" in outcome.content


async def test_write_rejects_escape(tmp_path):
    outcome = await WriteTool(tmp_path).run({"path": "../evil.txt", "content": "x"})
    assert outcome.is_error
    assert "cwd-jail" in outcome.content


async def test_bash_denies_network_binary(tmp_path):
    outcome = await BashTool(tmp_path, enabled=True).run({"command": "curl https://example.com"})
    assert outcome.is_error
    assert "denied" in outcome.content


def test_symlink_escape_rejected(tmp_path):
    import os

    from pico_core.tools import _ensure_within, _resolve

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "work" / "link.txt"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(outside, link)
    except OSError:
        import pytest

        pytest.skip("symlinks unavailable")
    assert _ensure_within(tmp_path / "work", _resolve(tmp_path / "work", "link.txt")) is None


async def test_jail_denial_traced_via_loop(tmp_path):
    from conftest import FakeProvider, make_session
    from pico_ai.types import StreamEvent, ToolCall

    call = ToolCall(id="c1", name="read", arguments={"path": "../evil.txt"})
    provider = FakeProvider([[StreamEvent(kind="tool_call", tool_call=call)]])
    session = make_session(provider, tmp_path)
    await session.run("read it")
    branch = session.session.active_branch()
    results = [n for n in branch if n.payload.kind == "tool_result"]
    assert results and results[0].payload.is_error
    assert "cwd-jail" in results[0].payload.content


def test_denial_payload_shape():
    from pico_core.session import denial_payload

    p = denial_payload("read", "error: path escapes cwd-jail: ../x")
    assert p.is_error and p.name == "read" and "cwd-jail" in p.content
