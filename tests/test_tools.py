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
