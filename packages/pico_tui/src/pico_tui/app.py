"""The interactive terminal UI (REPL) for pico."""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from typing import Any, Callable

from pico_sdk import (
    AgentSession,
    AssistantPayload,
    CompactionSummaryPayload,
    LoopEvent,
    ToolRequestPayload,
    ToolResultPayload,
    UserPayload,
)
from pico_sdk.config import load_settings
from pico_sdk.providers import create_provider

# ANSI escape codes (used only when color is enabled).
_RESET = "\033[0m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"


def _paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{_RESET}" if color else text


HELP = """\
Commands:
  /help              show this help
  /history           list session nodes (with indices for /fork)
  /compact [text]    summarise older turns (optionally with steering text)
  /fork <index|id>   rewind to a node and start a new branch
  /undo              rewind to the previous user turn
  /quit              save and exit
Anything else is sent to the agent as a prompt.\
"""


@dataclass
class Command:
    """A slash command parsed from a line of input."""

    kind: str  # "compact" | "fork" | "help" | "history" | "undo" | "quit"
    arg: str = ""


@dataclass
class Prompt:
    """A plain prompt to send to the agent."""

    text: str


def parse_line(line: str) -> Command | Prompt:
    """Parse a line of input into a command or a prompt."""
    line = line.strip()
    if line in ("/quit", "/exit", "/q"):
        return Command("quit")
    if line in ("/help", "/h", "/?"):
        return Command("help")
    if line in ("/history", "/nodes"):
        return Command("history")
    if line in ("/undo", "/back"):
        return Command("undo")
    if line.startswith("/compact"):
        return Command("compact", line[len("/compact") :].strip())
    if line.startswith("/fork"):
        return Command("fork", line[len("/fork") :].strip())
    return Prompt(line)


def _truncate(text: str, limit: int = 200) -> str:
    """Collapse whitespace and truncate long tool output for display."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


def _snippet(payload: Any) -> str:
    """Return a short, human-readable summary of a node payload."""
    if isinstance(payload, UserPayload):
        return payload.content
    if isinstance(payload, AssistantPayload):
        return payload.text
    if isinstance(payload, ToolRequestPayload):
        return f"{payload.tool_call.name} {payload.tool_call.arguments}"
    if isinstance(payload, ToolResultPayload):
        return payload.content
    if isinstance(payload, CompactionSummaryPayload):
        return payload.summary
    return ""


def render_event(event: LoopEvent, color: bool = False) -> str:
    """Render a loop event for the terminal; empty string means no output."""
    if event.kind == "text":
        return event.text
    if event.kind == "thinking":
        return _paint(event.thinking, _DIM, color)
    if event.kind == "tool_request" and event.tool_request is not None:
        call = event.tool_request.tool_call
        if call.name == "bash":
            return _paint("$ " + call.arguments.get("command", "") + "\n", _GREEN, color)
        return _paint(f"[{call.name}] {call.arguments}\n", _CYAN, color)
    if event.kind == "tool_result" and event.tool_result is not None:
        result = event.tool_result
        if result.name == "bash":
            return _paint(result.content.rstrip() + "\n", _DIM, color)
        snippet = _truncate(result.content)
        return _paint(f"  -> {snippet}\n", _DIM, color)
    if event.kind == "usage" and event.usage is not None:
        u = event.usage
        return _paint(f"  ({u.input_tokens} in, {u.output_tokens} out)\n", _DIM, color)
    return ""


class TUI:
    """An interactive, streaming terminal session."""

    def __init__(
        self,
        session: AgentSession,
        *,
        input_fn: Callable[[str], str] = input,
        write: Callable[[str], Any] = sys.stdout.write,
        color: bool = True,
    ) -> None:
        self.session = session
        self._input = input_fn
        self._write = write
        self._color = color

    async def run(self) -> None:
        self._write(
            _paint(
                f"pico - model={self.session.model}. /help for commands, /quit to exit.\n",
                _CYAN,
                self._color,
            )
        )
        while True:
            try:
                line = await asyncio.to_thread(self._input, "pico> ")
            except (EOFError, KeyboardInterrupt):
                line = "/quit"
            parsed = parse_line(line)
            if isinstance(parsed, Command):
                if parsed.kind == "quit":
                    break
                if parsed.kind == "help":
                    self._write(HELP + "\n")
                    continue
                if parsed.kind == "history":
                    self._history()
                    continue
                if parsed.kind == "undo":
                    self._undo()
                    continue
                if parsed.kind == "compact":
                    await self.session.compact(parsed.arg)
                    self._write("compacted context\n")
                    continue
                if parsed.kind == "fork":
                    self._fork(parsed.arg)
                    continue
                continue
            async for event in self.session.stream(parsed.text):
                self._write(render_event(event, color=self._color))
            self._write("\n")
        self.session.save()

    def _history(self) -> None:
        branch = self.session.session.active_branch()
        if not branch:
            self._write("(empty session)\n")
            return
        for i, node in enumerate(branch):
            marker = ">" if node.id == self.session.session.active_leaf_id else " "
            self._write(f"{marker} [{i}] {node.payload.kind}: {_truncate(_snippet(node.payload), 80)}\n")

    def _undo(self) -> None:
        branch = self.session.session.active_branch()
        users = [n for n in branch if isinstance(n.payload, UserPayload)]
        if len(users) < 2:
            self._write("nothing to undo\n")
            return
        target = users[-2]
        self.session.fork(target.id)
        self._write(f"rewound to user turn [{branch.index(target)}]\n")

    def _fork(self, arg: str) -> None:
        if not arg:
            self._write("usage: /fork <index-or-node-id>\n")
            return
        node_id = arg
        if arg.isdigit():
            branch = self.session.session.active_branch()
            idx = int(arg)
            if not (0 <= idx < len(branch)):
                self._write(f"error: no node at index {arg}\n")
                return
            node_id = branch[idx].id
        try:
            self.session.fork(node_id)
            self._write(f"forked to {node_id}\n")
        except KeyError:
            self._write(f"error: unknown node id: {arg}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pico-chat", description="Interactive pico session."
    )
    parser.add_argument("--allow-bash", action="store_true", help="Permit unsandboxed bash.")
    parser.add_argument("--model", default=None, help="Override the configured model.")
    parser.add_argument("--cwd", default=None, help="Working directory (default: current).")
    parser.add_argument("--session", default=None, help="Resume an existing session by id.")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output.")
    args = parser.parse_args(argv)

    settings = load_settings()
    model = args.model or settings.model
    provider = create_provider(settings)
    if args.session:
        session = AgentSession.load(
            args.session,
            provider=provider,
            model=model,
            settings=settings,
            working_dir=args.cwd,
            allow_bash=args.allow_bash,
        )
    else:
        session = AgentSession(
            provider=provider,
            model=model,
            settings=settings,
            working_dir=args.cwd,
            allow_bash=args.allow_bash,
        )
    tui = TUI(session, color=not args.no_color)
    asyncio.run(tui.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
