"""The interactive terminal UI (REPL) for pico."""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from typing import Any, Callable

from pico_core.fsm import LoopEvent
from pico_sdk.config import load_settings
from pico_sdk.providers import create_provider
from pico_sdk.session import AgentSession

HELP = """\
Commands:
  /help              show this help
  /compact [text]    summarise older turns (optionally with steering text)
  /fork <node-id>    rewind to an earlier node and start a new branch
  /quit              save and exit
Anything else is sent to the agent as a prompt.\
"""


@dataclass
class Command:
    """A slash command parsed from a line of input."""

    kind: str  # "compact" | "fork" | "help" | "quit"
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
    if line.startswith("/compact"):
        return Command("compact", line[len("/compact") :].strip())
    if line.startswith("/fork"):
        return Command("fork", line[len("/fork") :].strip())
    return Prompt(line)


def render_event(event: LoopEvent) -> str:
    """Render a loop event for the terminal; empty string means no output."""
    if event.kind == "text":
        return event.text
    if event.kind == "thinking":
        return ""
    if event.kind == "tool_request" and event.tool_request is not None:
        call = event.tool_request.tool_call
        if call.name == "bash":
            return "$ " + call.arguments.get("command", "") + "\n"
        return f"[{call.name}] {call.arguments}\n"
    if event.kind == "tool_result" and event.tool_result is not None:
        if event.tool_result.name == "bash":
            return event.tool_result.content.rstrip() + "\n"
        return ""
    return ""


class TUI:
    """An interactive, streaming terminal session."""

    def __init__(
        self,
        session: AgentSession,
        *,
        input_fn: Callable[[str], str] = input,
        write: Callable[[str], Any] = sys.stdout.write,
    ) -> None:
        self.session = session
        self._input = input_fn
        self._write = write

    async def run(self) -> None:
        self._write("pico - interactive coding agent. /help for commands, /quit to exit.\n")
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
                if parsed.kind == "compact":
                    await self.session.compact(parsed.arg)
                    self._write("compacted context\n")
                    continue
                if parsed.kind == "fork":
                    self._fork(parsed.arg)
                    continue
                continue
            async for event in self.session.stream(parsed.text):
                self._write(render_event(event))
            self._write("\n")
        self.session.save()

    def _fork(self, arg: str) -> None:
        if not arg:
            self._write("usage: /fork <node-id>\n")
            return
        try:
            self.session.fork(arg)
            self._write(f"forked to {arg}\n")
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
    tui = TUI(session)
    asyncio.run(tui.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
