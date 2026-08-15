"""The four core tools: read, write, edit, bash.

Each tool operates against a working directory. Bash runs unsandboxed and is
disabled unless an opt-in flag is set. Tool errors (missing file, non-zero exit)
surface as results rather than exceptions.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from pico_ai.types import ToolDefinition


class ToolOutcome(BaseModel):
    """The result of running a tool."""

    content: str
    is_error: bool = False


class Tool(Protocol):
    """A capability the agent can invoke."""

    name: str
    description: str
    input_schema: dict

    async def run(self, arguments: dict) -> ToolOutcome:
        """Execute the tool and return its outcome."""
        ...


def _resolve(cwd: Path, raw: str) -> Path:
    """Resolve a possibly-relative path against the working directory."""
    p = Path(raw)
    return p if p.is_absolute() else cwd / p


class ReadTool:
    """Read a file's contents."""

    name = "read"
    description = "Read the contents of a file."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def __init__(self, cwd: Path) -> None:
        self._cwd = cwd

    async def run(self, arguments: dict) -> ToolOutcome:
        path = _resolve(self._cwd, arguments["path"])
        try:
            return ToolOutcome(content=path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ToolOutcome(
                content=f"error: file not found: {arguments['path']}", is_error=True
            )
        except OSError as exc:
            return ToolOutcome(content=f"error: {exc}", is_error=True)


class WriteTool:
    """Create or overwrite a file."""

    name = "write"
    description = "Create or overwrite a file with the given content."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    def __init__(self, cwd: Path) -> None:
        self._cwd = cwd

    async def run(self, arguments: dict) -> ToolOutcome:
        path = _resolve(self._cwd, arguments["path"])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(arguments.get("content", ""), encoding="utf-8")
            return ToolOutcome(content=f"wrote {arguments['path']}")
        except OSError as exc:
            return ToolOutcome(content=f"error: {exc}", is_error=True)


class EditTool:
    """Apply a surgical search/replace patch to a file."""

    name = "edit"
    description = "Replace a unique occurrence of old_text with new_text in a file."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        "required": ["path", "old_text", "new_text"],
    }

    def __init__(self, cwd: Path) -> None:
        self._cwd = cwd

    async def run(self, arguments: dict) -> ToolOutcome:
        path = _resolve(self._cwd, arguments["path"])
        old = arguments["old_text"]
        new = arguments.get("new_text", "")
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ToolOutcome(
                content=f"error: file not found: {arguments['path']}", is_error=True
            )
        count = content.count(old)
        if count == 0:
            return ToolOutcome(content="error: old_text not found", is_error=True)
        if count > 1:
            return ToolOutcome(
                content=f"error: old_text found {count} times; provide a unique match",
                is_error=True,
            )
        try:
            path.write_text(content.replace(old, new, 1), encoding="utf-8")
            return ToolOutcome(content=f"edited {arguments['path']}")
        except OSError as exc:
            return ToolOutcome(content=f"error: {exc}", is_error=True)


class BashTool:
    """Run a shell command (unsandboxed, opt-in)."""

    name = "bash"
    description = "Run a shell command and return its output and exit code."
    input_schema = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    }

    def __init__(self, cwd: Path, enabled: bool = False) -> None:
        self._cwd = cwd
        self.enabled = enabled

    async def run(self, arguments: dict) -> ToolOutcome:
        if not self.enabled:
            return ToolOutcome(
                content="error: bash is disabled; pass --allow-bash to enable",
                is_error=True,
            )
        command = arguments["command"]
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self._cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
            content = output.rstrip() + f"\n[exit code: {proc.returncode}]"
            return ToolOutcome(content=content, is_error=proc.returncode != 0)
        except Exception as exc:  # noqa: BLE001 - surface any failure as a result
            return ToolOutcome(content=f"error: {exc}", is_error=True)


class ToolRegistry:
    """A name → tool mapping that also exposes tool definitions."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=t.name, description=t.description, input_schema=t.input_schema
            )
            for t in self._tools.values()
        ]

