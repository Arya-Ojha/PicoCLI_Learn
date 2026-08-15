"""The ``pico`` command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from pico_core.fsm import LoopEvent

from .config import load_settings
from .session import AgentSession


def format_event(event: LoopEvent) -> str | None:
    """Return the text to print for an event, or ``None`` to print nothing."""
    if event.kind == "text":
        return event.text
    if event.kind == "tool_request" and event.tool_request is not None:
        if event.tool_request.tool_call.name == "bash":
            return "$ " + event.tool_request.tool_call.arguments.get("command", "") + "\n"
    if event.kind == "tool_result" and event.tool_result is not None:
        if event.tool_result.name == "bash":
            return event.tool_result.content.rstrip() + "\n"
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pico", description="A headless coding agent.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the agent on a prompt.")
    run.add_argument("prompt", nargs="+", help="The prompt to run.")
    run.add_argument("--allow-bash", action="store_true", help="Permit unsandboxed bash.")
    run.add_argument("--model", default=None, help="Override the configured model.")
    run.add_argument("--cwd", default=None, help="Working directory (default: current).")
    run.add_argument("--session", default=None, help="Resume an existing session by id.")
    return parser


async def run_command(args: argparse.Namespace) -> int:
    settings = load_settings()
    model = args.model or settings.model
    api_key = os.environ.get(settings.api_key_env, "")

    from pico_ai.openrouter import OpenRouterProvider

    provider = OpenRouterProvider(api_key=api_key)
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
    prompt = " ".join(args.prompt)
    if prompt.startswith("/compact"):
        instructions = prompt[len("/compact") :].strip()
        await session.compact(instructions)
        sys.stdout.write("compacted context\n")
        session.save()
        return 0
    async for event in session.stream(prompt):
        rendered = format_event(event)
        if rendered:
            sys.stdout.write(rendered)
            sys.stdout.flush()
    sys.stdout.write("\n")
    session.save()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return asyncio.run(run_command(args))
    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
