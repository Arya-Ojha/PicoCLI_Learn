"""Smoke: core tools read + bash."""

from pico_core.tools import BashTool, ReadTool


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
