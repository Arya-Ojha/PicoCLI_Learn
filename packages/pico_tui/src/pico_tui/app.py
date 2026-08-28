"""Textual-based interactive terminal UI for pico."""

from __future__ import annotations

import argparse
import asyncio
import sys

from collections.abc import Callable

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, RichLog

from pico_sdk import (
    AgentSession,
    AssistantPayload,
    CompactionSummaryPayload,
    Mode,
    ToolRequestPayload,
    ToolResultPayload,
    UserPayload,
)
from pico_sdk.config import load_settings
from pico_sdk.providers import create_provider

from .commands import Command, Prompt, parse_line
from .render import _truncate, render_event
from .status_bar import ContextStatusBar

HELP_TEXT = """\
[bold]Commands (slash or key binding):[/]
  [cyan]/help, F1[/]        show this help
  [cyan]/history, Ctrl+H[/] list session nodes (with indices for /fork)
  [cyan]/compact, Ctrl+K[/] summarise older turns (optionally with steering text)
  [cyan]/model <name>[/]   change the LLM model for this session
  [cyan]/fork <n|id>[/]     rewind to a node and start a new branch
  [cyan]/undo, Ctrl+Z[/]    rewind to the previous user turn
  [cyan]/learn, Tab[/]      toggle between act mode and learn mode
  [cyan]/quit, Ctrl+Q[/]    save and exit
Messages you send go in whichever mode is active; press Tab to switch.\
"""


def _snippet(payload: object) -> str:
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


class _SessionManager:
    """Holds the AgentSession and provides command methods called by the app."""

    def __init__(self, session: AgentSession) -> None:
        self.session = session

    async def stream(
        self, prompt: str, on_event: Callable[[object], None], *, mode: Mode = "act"
    ) -> None:
        """Consume the agent stream, calling on_event for each LoopEvent.

        Text and thinking chunks are buffered separately and flushed as single
        Text renderables when a non-streaming event arrives (or the stream ends),
        avoiding one-chunk-per-line output in RichLog.
        """
        text_buffer: list[str] = []
        thinking_buffer: list[str] = []

        def _flush() -> None:
            if text_buffer:
                on_event(Text("".join(text_buffer)))
                text_buffer.clear()
            if thinking_buffer:
                on_event(Text("".join(thinking_buffer), style="dim italic"))
                thinking_buffer.clear()

        async for event in self.session.stream(prompt, mode=mode):
            if event.kind == "text":
                text_buffer.append(event.text)
            elif event.kind == "thinking":
                thinking_buffer.append(event.thinking)
            else:
                _flush()
                rendered = render_event(event)
                if rendered is not None:
                    on_event(rendered)
        _flush()

    def history_text(self) -> Table | None:
        """Return a Rich Table of nodes, or None if session is empty."""
        branch = self.session.session.active_branch()
        if not branch:
            return None
        table = Table(box=None, show_header=False, padding=(0, 1))
        table.add_column("", width=2)
        table.add_column("#", width=5, justify="right")
        table.add_column("kind", width=12)
        table.add_column("summary")
        for i, node in enumerate(branch):
            marker = "\u25b6" if node.id == self.session.session.active_leaf_id else ""
            table.add_row(
                marker,
                str(i),
                node.payload.kind,
                _truncate(_snippet(node.payload), 80),
            )
        return table

    def undo(self) -> str | None:
        """Return a message or None."""
        branch = self.session.session.active_branch()
        users = [n for n in branch if isinstance(n.payload, UserPayload)]
        if len(users) < 2:
            return "nothing to undo"
        target = users[-2]
        self.session.fork(target.id)
        return f"rewound to user turn [{branch.index(target)}]"

    async def compact(self, arg: str) -> str:
        await self.session.compact(arg)
        return "compacted context"

    def model(self, arg: str) -> str:
        if not arg:
            return f"current model: {self.session.model}"
        self.session.model = arg
        self.session.loop.model = arg
        return f"switched to model: {arg}"

    def fork(self, arg: str) -> str:
        branch = self.session.session.active_branch()
        node_id = arg
        if arg.isdigit():
            idx = int(arg)
            if not (0 <= idx < len(branch)):
                return f"error: no node at index {arg}"
            node_id = branch[idx].id
        try:
            self.session.fork(node_id)
            return f"forked to {node_id}"
        except KeyError:
            return f"error: unknown node id: {arg}"



class PicoApp(App[None]):
    """The pico interactive agent TUI."""

    CSS = """
    #chat-log {
        height: 1fr;
        border: none;
    }
    #chat-log:focus {
        border: none;
    }
    #input-bar {
        margin: 0 1;
    }
    #status-bar {
        height: 1;
        width: 100%;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit_app", "Quit"),
        ("ctrl+h", "show_history", "History"),
        ("ctrl+z", "undo", "Undo"),
        ("ctrl+k", "compact", "Compact"),
        ("f1", "show_help", "Help"),
        # Priority so it wins over the Screen's Tab focus-traversal binding.
        Binding("tab", "toggle_learn", "Mode", priority=True),
    ]

    def __init__(self, mgr: _SessionManager) -> None:
        super().__init__()
        self._mgr = mgr
        self._streaming = False
        self._mode: Mode = "act"

    # -- mode helpers --

    def _mode_badge(self) -> str:
        """The visible mode badge: '[learn]' or '[act]'."""
        return "[learn]" if self._mode == "learn" else "[act]"

    def _placeholder(self) -> str:
        return f"pico>  {self._mode_badge()}  (type a prompt, or /help for commands)"

    def get_key_display(self, binding: Binding) -> str:
        """Show the mode badge where the footer normally shows the Tab key."""
        if binding.action == "toggle_learn":
            return self._mode_badge()
        return super().get_key_display(binding)

    def action_toggle_learn(self) -> None:
        """Flip between act and learn mode and reflect it in the UI."""
        self._mode = "act" if self._mode == "learn" else "learn"
        self.refresh_bindings()  # footer re-reads get_key_display for the badge
        self.query_one("#input-bar", Input).placeholder = self._placeholder()

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
        yield Input(
            id="input-bar",
            placeholder=self._placeholder(),
        )
        yield ContextStatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the input bar on start and initialize status bar."""
        self.query_one("#input-bar", Input).focus()
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        """Update the status bar with current session info."""
        try:
            status_bar = self.query_one("#status-bar", ContextStatusBar)
            status_bar.update_info(
                provider=self._mgr.session.provider_name,
                model=self._mgr.session.model,
                tokens=self._mgr.session.estimate_tokens(),
                context_window=self._mgr.session.context_window,
                thinking=self._streaming,
            )
        except Exception as e:
            # If status bar update fails, don't crash the app
            # Just log it to the chat log for debugging
            try:
                chat_log = self.query_one("#chat-log", RichLog)
                chat_log.write(Text(f"[Status bar error: {e}]", style="red"))
            except Exception:
                pass

    # -- input handling --

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle a line submitted in the input bar."""
        input_widget = self.query_one("#input-bar", Input)
        input_widget.clear()

        if self._streaming:
            self._write_chat(
                Text("(still streaming - please wait)", style="dim italic")
            )
            return

        parsed = parse_line(event.value)
        if isinstance(parsed, Command):
            await self._dispatch_command(parsed)
        elif parsed.text:  # non-empty prompt
            await self._run_prompt(parsed.text)

    # -- command dispatch --

    async def _dispatch_command(self, cmd: Command) -> None:
        if cmd.kind == "quit":
            self._mgr.session.save()
            self.exit()
        elif cmd.kind == "help":
            self._write_chat(Panel(HELP_TEXT, title="Help"))
        elif cmd.kind == "history":
            hist = self._mgr.history_text()
            if hist is None:
                self._write_chat(Text("(empty session)", style="dim"))
            else:
                self._write_chat(hist)
        elif cmd.kind == "undo":
            msg = self._mgr.undo()
            self._write_chat(Text(msg or "(undo)", style="dim"))
        elif cmd.kind == "compact":
            msg = await self._mgr.compact(cmd.arg)
            self._write_chat(Text(msg, style="dim"))
            self._update_status_bar()
        elif cmd.kind == "model":
            msg = self._mgr.model(cmd.arg)
            self._write_chat(Text(msg, style="dim"))
            self._update_status_bar()
        elif cmd.kind == "fork":
            msg = self._mgr.fork(cmd.arg)
            self._write_chat(Text(msg, style="dim"))
        elif cmd.kind == "learn":
            self.action_toggle_learn()

    # -- prompt to agent streaming --

    async def _run_prompt(self, text: str) -> None:
        """Send a user prompt to the agent in the current mode and stream it."""
        self._write_chat(Text(f"> {text}", style="bold"))
        self._streaming = True
        self._update_status_bar()
        asyncio.create_task(self._stream_worker(text, self._mode))

    async def _stream_worker(self, prompt: str, mode: Mode) -> None:
        """Background task that consumes the agent stream."""
        try:
            chat_log = self.query_one("#chat-log", RichLog)

            def _write(renderable: object) -> None:
                chat_log.write(renderable)

            await self._mgr.stream(prompt, _write, mode=mode)
        except Exception as exc:
            chat_log = self.query_one("#chat-log", RichLog)
            chat_log.write(
                Panel(str(exc), title="error", border_style="red")
            )
        finally:
            self._streaming = False
            self._update_status_bar()

    # -- helpers --

    def _write_chat(self, renderable: object) -> None:
        self.query_one("#chat-log", RichLog).write(renderable)

    # -- key binding actions --

    async def action_quit_app(self) -> None:
        self._mgr.session.save()
        self.exit()

    async def action_show_history(self) -> None:
        await self._dispatch_command(Command("history"))

    async def action_undo(self) -> None:
        await self._dispatch_command(Command("undo"))

    async def action_compact(self) -> None:
        await self._dispatch_command(Command("compact", ""))

    async def action_show_help(self) -> None:
        await self._dispatch_command(Command("help"))


# -- CLI entry point --


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pico-chat", description="Interactive pico session (Textual TUI)."
    )
    parser.add_argument(
        "--no-bash",
        action="store_true",
        help="Disable unsandboxed bash (on by default).",
    )
    parser.add_argument(
        "--model", default=None, help="Override the configured model."
    )
    parser.add_argument(
        "--cwd", default=None, help="Working directory (default: current)."
    )
    parser.add_argument(
        "--session", default=None, help="Resume an existing session by id."
    )
    parser.add_argument(
        "--strict-learn",
        action="store_true",
        help="Harden learn mode: block writes outside the lessons directory.",
    )
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
            allow_bash=not args.no_bash,
            strict_learn=args.strict_learn,
        )
    else:
        session = AgentSession(
            provider=provider,
            model=model,
            settings=settings,
            working_dir=args.cwd,
            allow_bash=not args.no_bash,
            strict_learn=args.strict_learn,
        )
    mgr = _SessionManager(session)
    app = PicoApp(mgr)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
