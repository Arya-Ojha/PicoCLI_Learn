"""Rich-based event renderer for LoopEvent → Rich renderable."""

from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache

from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from pico_sdk import LoopEvent

# Active Pygments theme for code blocks. The app sets this from settings at
# startup and on /theme; it defaults to monokai.
CODE_THEME: str = "monokai"

# Curated suggestions shown by /theme; any pygments style is accepted.
THEME_SUGGESTIONS: tuple[str, ...] = (
    "monokai",
    "dracula",
    "github-dark",
    "gruvbox-dark",
    "one-dark",
    "nord",
    "vs",
    "gruvbox-light",
)


@lru_cache(maxsize=1)
def available_themes() -> frozenset[str]:
    """Return every code theme pygments ships (lowercased)."""
    from pygments.styles import get_all_styles  # type: ignore[import-untyped]

    return frozenset(s.lower() for s in get_all_styles())


def set_code_theme(name: str) -> bool:
    """Activate a code theme; return False (leaving CODE_THEME) if unknown."""
    global CODE_THEME
    if name.lower() not in available_themes():
        return False
    CODE_THEME = name.lower()
    return True

# Distinct heading colors per tool type.
_TOOL_COLORS: dict[str, str] = {
    "bash": "green",
    "read": "bright_blue",
    "write": "yellow",
    "edit": "magenta",
    "todo_write": "cyan",
}


def _truncate(text: str, limit: int = 200) -> str:
    """Collapse whitespace and truncate long tool output."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


_EXIT_CODE_RE = re.compile(r"\[exit code: (-?\d+)\]")


def bash_status(content: str, is_error: bool) -> tuple[str, str]:
    """Return (short label, color) for a bash result; output itself stays hidden.

    The full command output remains in the session for the model — the UI
    only shows whether it passed or failed.
    """
    match = _EXIT_CODE_RE.search(content)
    code = match.group(1) if match else None
    if not is_error:
        label = f"passed{f' [exit code: {code}]' if code is not None else ''}"
        return label, "green"
    label = f"error{f' [exit code: {code}]' if code is not None else ''}"
    return label, "red"


def render_event(event: LoopEvent):  # -> RenderableType (kept loose for mypy simplicity)
    """Convert a LoopEvent to a Rich renderable for display in a RichLog.

    Returns None when the event should produce no visible output.
    """
    if event.kind == "text":
        return (
            Markdown(event.text)
            if _looks_like_markdown(event.text)
            else Text(event.text)
        )
    if event.kind == "thinking":
        return Text(event.thinking, style="dim italic")
    if event.kind == "tool_request" and event.tool_request is not None:
        call = event.tool_request.tool_call
        if call.name == "todo_write":
            # The checklist result says it all — the big args dump is noise.
            return None
        color = _TOOL_COLORS.get(call.name, "cyan")
        if call.name == "bash":
            cmd = call.arguments.get("command", "")
            return Panel(
                cmd,
                title=f"[bold {color}]{call.name}[/]",
                border_style=color,
                title_align="left",
            )
        if call.name in ("edit", "write"):
            return _diff_group(call.name, call.arguments, color)
        if call.name == "read":
            path = str(call.arguments.get("path", ""))
            return _tool_heading("read", path, color)
        return Panel(
            _pretty_args(call.arguments),
            title=f"[bold {color}]{call.name}[/]",
            border_style=color,
            title_align="left",
        )
    if event.kind == "tool_result" and event.tool_result is not None:
        result = event.tool_result
        color = _TOOL_COLORS.get(result.name, "dim cyan")
        if result.name == "bash":
            label, color = bash_status(result.content, result.is_error)
            return Panel(
                label,
                title=f"[{color}]{result.name} result[/]",
                border_style=color,
                title_align="left",
            )
        if result.name == "todo_write" and not result.is_error:
            # Checklists are short by nature — show the full list, not a snippet.
            return Panel(
                Text(result.content),
                title=f"[{color}]todos[/]",
                border_style=color,
                title_align="left",
            )
        if result.name in ("read", "write", "edit"):
            # The request already showed everything (diff / path) — the
            # "edited <path>" receipt is noise.
            return None
        snippet = _truncate(result.content)
        return Panel(
            snippet,
            title=f"[{color}]{result.name} result[/]",
            border_style=color,
            title_align="left",
        )
    if event.kind == "usage" and event.usage is not None:
        u = event.usage
        return Text(f"({u.input_tokens}↓ {u.output_tokens}↑)", style="dim")
    return None


def _looks_like_markdown(text: str) -> bool:
    """Heuristic: use Rich Markdown for multi-line or formatted responses."""
    return "\n" in text or any(
        marker in text for marker in ("```", "**", "# ", "- ", "1. ", "|")
    )


_REMOVED_BG = "#3a1c1c"
_ADDED_BG = "#1c3a22"

_EXTENSION_LEXERS = {
    "py": "python", "js": "javascript", "ts": "typescript",
    "html": "html", "css": "css", "json": "json", "md": "markdown",
    "yml": "yaml", "yaml": "yaml", "toml": "toml", "rs": "rust",
    "go": "go", "java": "java", "c": "c", "cpp": "cpp", "sh": "bash",
}


def _lexer_for(path: str) -> str:
    """Guess the code lexer from the file extension (VS Code-style colors)."""
    filename = path.rsplit("/", 1)[-1]
    if "." in filename and (ext := filename.split(".")[-1].lower()):
        if lexer := _EXTENSION_LEXERS.get(ext):
            return lexer
    return "text"


def _code_block(code: str, lexer: str, background: str) -> Syntax:
    """A syntax-highlighted block whose background fills the full line width."""
    return Syntax(
        code,
        lexer,
        theme=CODE_THEME,
        word_wrap=True,
        background_color=background,
    )


def _diff_parts(old: str, new: str, lexer: str) -> list:
    """Align old vs new lines: red removals, green additions, dim context.

    Removed/added hunks render as syntax-highlighted blocks with full-width
    backgrounds; unchanged lines stay plain dim text.
    """
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    parts: list = []
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                parts.append(Text("  " + line, style="dim"))
        if tag in ("delete", "replace"):
            removed = "\n".join("- " + line for line in old_lines[i1:i2])
            parts.append(_code_block(removed, lexer, _REMOVED_BG))
        if tag in ("insert", "replace"):
            added = "\n".join("+ " + line for line in new_lines[j1:j2])
            parts.append(_code_block(added, lexer, _ADDED_BG))
    if not parts:
        parts.append(Text("(no changes)", style="dim"))
    return parts


def _tool_heading(name: str, path: str, color: str) -> Text:
    """A borderless heading: bold tool name in its color, plain path."""
    heading = Text()
    heading.append(name, style=f"bold {color}")
    if path:
        heading.append(f" {path}")
    return heading


def _diff_group(name: str, arguments: dict, color: str) -> Group:
    """Format an edit/write request as a bare diff group (no panel border).

    ``edit`` aligns old_text → new_text hunk by hunk; ``write`` treats the
    whole content as added (there is no old text for a fresh file).
    """
    path = str(arguments.get("path", ""))
    if name == "edit":
        old = str(arguments.get("old_text", ""))
        new = str(arguments.get("new_text", ""))
    else:
        old, new = "", str(arguments.get("content", ""))
    header = _tool_heading(name, path, color)
    return Group(header, *_diff_parts(old, new, _lexer_for(path)))


def _pretty_args(arguments: dict) -> str:
    """Indent-2 JSON dump so other tools' args stay readable."""
    try:
        return json.dumps(arguments, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(arguments)
