"""Ticket 03 — the four core tools against a temporary working directory."""

from pathlib import Path

from pico_core.tools import BashTool, EditTool, ReadTool, WriteTool


async def test_read_existing_file(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    outcome = await ReadTool(tmp_path).run({"path": "a.txt"})
    assert outcome.content == "hello"
    assert not outcome.is_error


async def test_read_missing_file_is_error(tmp_path):
    outcome = await ReadTool(tmp_path).run({"path": "missing.txt"})
    assert outcome.is_error
    assert "not found" in outcome.content


async def test_write_creates_file(tmp_path):
    outcome = await WriteTool(tmp_path).run({"path": "sub/b.txt", "content": "data"})
    assert not outcome.is_error
    assert (tmp_path / "sub" / "b.txt").read_text(encoding="utf-8") == "data"


async def test_write_overwrites_file(tmp_path):
    (tmp_path / "c.txt").write_text("old", encoding="utf-8")
    await WriteTool(tmp_path).run({"path": "c.txt", "content": "new"})
    assert (tmp_path / "c.txt").read_text(encoding="utf-8") == "new"


async def test_edit_replaces_unique_match(tmp_path):
    (tmp_path / "d.txt").write_text("aaa bbb aaa", encoding="utf-8")
    outcome = await EditTool(tmp_path).run(
        {"path": "d.txt", "old_text": "bbb", "new_text": "ccc"}
    )
    assert not outcome.is_error
    assert (tmp_path / "d.txt").read_text(encoding="utf-8") == "aaa ccc aaa"


async def test_edit_missing_file_is_error(tmp_path):
    outcome = await EditTool(tmp_path).run(
        {"path": "nope.txt", "old_text": "x", "new_text": "y"}
    )
    assert outcome.is_error


async def test_edit_not_found_is_error(tmp_path):
    (tmp_path / "e.txt").write_text("abc", encoding="utf-8")
    outcome = await EditTool(tmp_path).run(
        {"path": "e.txt", "old_text": "zzz", "new_text": "y"}
    )
    assert outcome.is_error
    assert "not found" in outcome.content


async def test_edit_multiple_matches_is_error(tmp_path):
    (tmp_path / "f.txt").write_text("x x", encoding="utf-8")
    outcome = await EditTool(tmp_path).run(
        {"path": "f.txt", "old_text": "x", "new_text": "y"}
    )
    assert outcome.is_error
    assert "unique" in outcome.content


async def test_bash_disabled_is_error(tmp_path):
    outcome = await BashTool(tmp_path, enabled=False).run({"command": "echo hi"})
    assert outcome.is_error
    assert "disabled" in outcome.content


async def test_bash_runs_and_captures_output(tmp_path):
    outcome = await BashTool(tmp_path, enabled=True).run({"command": "echo hi"})
    assert not outcome.is_error
    assert "hi" in outcome.content
    assert "[exit code: 0]" in outcome.content


async def test_bash_nonzero_exit_is_error(tmp_path):
    outcome = await BashTool(tmp_path, enabled=True).run({"command": "exit 3"})
    assert outcome.is_error
    assert "[exit code: 3]" in outcome.content
