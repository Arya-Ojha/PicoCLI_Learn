"""The ``pico`` command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from pico_core.fsm import LoopEvent

import re as _re

from .config import load_settings, save_settings
from .providers import (
    FREE_MODEL_ALIAS,
    create_provider,
    resolve_free_model,
    resolve_model,
)
from .session import AgentSession

_EXIT_CODE_RE = _re.compile(r"\[exit code: (-?\d+)\]")


def _format_todo_list(content: str) -> str:
    """Render a todo_write result as a bare checklist (no tool chrome).

    The active item is wrapped in green ANSI (honoring NO_COLOR); completed
    and pending items print plain. Marks stay ASCII: stdout on Windows may
    be cp1252, where [✓]/[•] glyphs crash the write.
    """
    use_color = not os.environ.get("NO_COLOR")
    lines = ["# Todos"]
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[>]") and use_color:
            lines.append(f"\x1b[32m{line}\x1b[0m")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def format_event(event: LoopEvent) -> str | None:
    """Return the text to print for an event, or ``None`` to print nothing."""
    if event.kind == "text":
        return event.text
    if event.kind == "tool_request" and event.tool_request is not None:
        if event.tool_request.tool_call.name == "bash":
            return "$ " + event.tool_request.tool_call.arguments.get("command", "") + "\n"
    if event.kind == "tool_result" and event.tool_result is not None:
        if event.tool_result.name == "bash":
            match = _EXIT_CODE_RE.search(event.tool_result.content)
            code = match.group(1) if match else None
            suffix = f" [exit code: {code}]" if code is not None else ""
            if event.tool_result.is_error:
                return f"bash error{suffix}\n"
            return f"bash passed{suffix}\n"
        if event.tool_result.name == "todo_write" and not event.tool_result.is_error:
            return _format_todo_list(event.tool_result.content)
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pico", description="Self-hosted workbench runner.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the agent on a prompt.")
    run.add_argument("prompt", nargs="+", help="The prompt to run.")
    run.add_argument(
        "--no-bash",
        action="store_true",
        help="Disable bash (cwd-jailed, on by default).",
    )
    run.add_argument("--model", default=None, help="Override the configured model.")
    run.add_argument(
        "--provider",
        default=None,
        choices=["local", "openrouter"],
        help="Override the configured backend (default: from settings).",
    )
    run.add_argument(
        "--base-url",
        default=None,
        help="Override the local server endpoint (e.g. http://127.0.0.1:11434).",
    )
    run.add_argument("--cwd", default=None, help="Working directory (default: current).")
    run.add_argument("--session", default=None, help="Resume an existing session by id.")
    return parser


async def run_command(args: argparse.Namespace) -> int:
    settings = load_settings()
    if getattr(args, "provider", None):
        settings.provider = args.provider
    if getattr(args, "base_url", None):
        from pico_ai.local import normalize_base_url

        try:
            settings.base_url = normalize_base_url(args.base_url)
        except ValueError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 1
        settings.provider = "local"
    provider = create_provider(settings)

    if (settings.provider or "local").lower() == "openrouter":
        # Cloud backend, kept for testing: still needs its API key.
        api_key = os.environ.get(settings.api_key_env, "")
        if not api_key:
            sys.stderr.write(
                f"error: {settings.api_key_env} is not set.\n"
                f"Set it before running pico, e.g.:\n"
                f'  $env:{settings.api_key_env} = "sk-or-v1-..."\n'
            )
            return 1
        model = args.model or settings.model
        if model == FREE_MODEL_ALIAS:
            resolved = await resolve_free_model(provider)
            if resolved:
                model = resolved
                sys.stdout.write(f"using free model: {model}\n")
    elif args.model:
        model = args.model
    else:
        # Local backend: auto-detect the served model.
        model, served = await resolve_model(provider, settings)
        ids = [m.get("id", "") for m in served if m.get("id")]
        if not served:
            sys.stderr.write(
                f"warning: no local models detected at {settings.base_url}; "
                f"is the server running? using '{model}'.\n"
            )
        else:
            if (settings.model or "").strip() not in ids:
                # Remember the pick so the next launch skips detection.
                settings.model = model
                try:
                    save_settings(settings)
                except OSError:
                    pass
            if len(ids) > 1:
                sys.stdout.write(
                    "served models: "
                    + ", ".join(ids)
                    + f"\nusing {model} (change anytime with /model)\n"
                )
            else:
                sys.stdout.write(f"using local model: {model}\n")
    if args.session:
        session = AgentSession.load(
            args.session,
            provider=provider,
            model=model,
            settings=settings,
            working_dir=args.cwd,
            allow_bash=not args.no_bash,
        )
    else:
        session = AgentSession(
            provider=provider,
            model=model,
            settings=settings,
            working_dir=args.cwd,
            allow_bash=not args.no_bash,
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
