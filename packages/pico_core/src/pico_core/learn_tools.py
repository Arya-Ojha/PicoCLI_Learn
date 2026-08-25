"""Learn-mode tools: fetch, web search, lesson pages, and the strict guard.

These tools support **learn mode** (see CONTEXT.md). The lesson tool writes
self-contained HTML lesson pages with an interactive quiz under a dedicated,
per-topic directory inside the working directory. Fetch and web search let the
agent research real material; they use a stdlib-backed, injectable transport so
tests never touch the network. The guarded write/edit tools enforce 'never
author the learner's code' behind --strict-learn by blocking any write outside
the lessons directory.
"""

from __future__ import annotations

import asyncio
import re
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib import parse as _urlparse
from urllib import request as _urlrequest

from .tools import EditTool, ToolOutcome, WriteTool

# The directory (relative to the working directory) under which lessons live.
LESSONS_DIR_NAME = "pico-lessons"

# The tool result surfaced when the strict guard stops a non-lesson write.
BLOCKED_IN_LEARN_MODE = (
    "blocked in learn mode: pico doesn't write the learner's code — explain instead"
)

# DuckDuckGo's no-API-key HTML search endpoint.
DUCKDUCKGO_SEARCH_URL = "https://html.duckduckgo.com/html/?q="


def _slugify(text: str) -> str:
    """Collapse a string to a lowercase, path-safe slug (alnum, '-' and '_')."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-_") or "topic"


def _resolve(cwd: Path, raw: str) -> Path:
    """Resolve a possibly-relative path against the working directory."""
    p = Path(raw)
    return p if p.is_absolute() else cwd / p


def is_within_lessons_dir(cwd: Path, raw: str) -> bool:
    """Return True when ``raw`` resolves inside ``cwd / LESSONS_DIR_NAME``."""
    resolved = _resolve(cwd, raw).resolve()
    lessons_root = (cwd / LESSONS_DIR_NAME).resolve()
    return resolved == lessons_root or lessons_root in resolved.parents


def _blocked_if_outside(cwd: Path, raw: str) -> ToolOutcome | None:
    """Return the blocked outcome when ``raw`` is not under the lessons directory."""
    if is_within_lessons_dir(cwd, raw):
        return None
    return ToolOutcome(content=BLOCKED_IN_LEARN_MODE, is_error=True)


# ── HTTP transport seam (injectable, network-free in tests) ─────────────


@dataclass
class HttpResponse:
    """A minimal HTTP response: status code plus decoded body text."""

    status: int
    text: str


class HttpTransport(Protocol):
    """An async transport that performs a GET and returns an HttpResponse."""

    async def get(self, url: str) -> HttpResponse:  # pragma: no cover - protocol
        ...


class UrllibTransport:
    """Default stdlib-backed transport (runs blocking urllib in a thread)."""

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    async def get(self, url: str) -> HttpResponse:
        return await asyncio.to_thread(self._get_sync, url)

    def _get_sync(self, url: str) -> HttpResponse:
        req = _urlrequest.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (pico-learn)"}
        )
        with _urlrequest.urlopen(req, timeout=self._timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            text = resp.read().decode("utf-8", errors="replace")
        return HttpResponse(status=status, text=text)


# ── fetch ───────────────────────────────────────────────────────────────


class FetchTool:
    """Fetch the text of a web page at a URL."""

    name = "fetch"
    description = "Fetch the text of a web page (HTML/markdown) at a URL."
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    def __init__(self, transport: HttpTransport | None = None) -> None:
        self._transport = transport or UrllibTransport()

    async def run(self, arguments: dict) -> ToolOutcome:
        url = arguments.get("url", "")
        try:
            result = await self._transport.get(url)
        except Exception as exc:  # noqa: BLE001 - surface as a result
            return ToolOutcome(content=f"error: {exc}", is_error=True)
        if result.status != 200:
            return ToolOutcome(
                content=f"error: HTTP {result.status} for {url}", is_error=True
            )
        return ToolOutcome(content=result.text)


# ── web search (DuckDuckGo HTML, zero API keys) ─────────────────────────


class _DDGParser(HTMLParser):
    """Extract result titles/URLs and snippets from DuckDuckGo's HTML page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._in_title = False
        self._in_snippet = False
        self._title_parts: list[str] = []
        self._snippet_text: list[str] = []
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "a":
            return
        classes = dict(attrs).get("class", "") or ""
        if "result__a" in classes:
            self._in_title = True
            self._href = dict(attrs).get("href")
        elif "result__snippet" in classes:
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag != "a":
            return
        if self._in_title:
            self.results.append(
                {
                    "title": "".join(self._title_parts).strip(),
                    "url": self._href or "",
                    "snippet": "",
                }
            )
            self._in_title = False
            self._title_parts = []
            self._href = None
        elif self._in_snippet:
            if self.results:
                self.results[-1]["snippet"] = "".join(self._snippet_text).strip()
            self._in_snippet = False
            self._snippet_text = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        elif self._in_snippet:
            self._snippet_text.append(data)


def parse_duckduckgo_results(html: str) -> list[dict]:
    """Parse DuckDuckGo's HTML search page into [{title,url,snippet}, ...]."""
    parser = _DDGParser()
    parser.feed(html)
    parser.close()
    return parser.results


class SearchTool:
    """Search the web via DuckDuckGo's no-API-key HTML endpoint."""

    name = "search"
    description = (
        "Search the web for a topic and return matching titles, URLs, and snippets."
    )
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    def __init__(
        self,
        transport: HttpTransport | None = None,
        endpoint: str = DUCKDUCKGO_SEARCH_URL,
    ) -> None:
        self._transport = transport or UrllibTransport()
        self._endpoint = endpoint

    async def run(self, arguments: dict) -> ToolOutcome:
        query = arguments.get("query", "")
        url = self._endpoint + _urlparse.quote(query)
        try:
            result = await self._transport.get(url)
        except Exception as exc:  # noqa: BLE001 - surface as a result
            return ToolOutcome(content=f"error: {exc}", is_error=True)
        if result.status != 200:
            return ToolOutcome(
                content=f"error: HTTP {result.status} for search", is_error=True
            )
        results = parse_duckduckgo_results(result.text)
        if not results:
            return ToolOutcome(content=f"no results for: {query}")
        lines = []
        for item in results:
            lines.append(f"- {item['title']}\n  {item['url']}\n  {item['snippet']}")
        return ToolOutcome(content="\n".join(lines))


# ── lesson pages ────────────────────────────────────────────────────────

_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: system-ui, sans-serif; max-width: 46rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }}
header.page {{ border-bottom: 2px solid; padding-bottom: 0.5rem; margin-bottom: 1.5rem; }}
h1 {{ margin: 0 0 0.25rem 0; }}
.meta {{ opacity: 0.7; font-size: 0.9rem; }}
pre, code {{ background: rgba(0,0,0,0.06); border-radius: 6px; padding: 0 4px; }}
pre {{ padding: 1rem; overflow-x: auto; }}
.lesson-content pre>code {{ background: none; padding: 0; }}
.quiz-item {{ border: 1px solid; border-radius: 10px; padding: 1rem; margin: 1rem 0; }}
.quiz-item .quiz-answer {{ font-weight: 600; margin-top: 0.5rem; }}
.quiz-item.correct {{ border-color: green; }}
.quiz-item.incorrect {{ border-color: red; }}
</style>
</head>
<body>
<header class="page">
<h1>{topic}</h1>
<div class="meta">Lesson {number} &mdash; {title}</div>
</header>
<main class="lesson-content">
{content}
</main>
<script>
// Self-checking quiz: any .quiz-item[data-answer] compares its visible answer
// text against the expected answer on load and marks itself right/wrong.
document.querySelectorAll(".quiz-item").forEach(function (item) {{
  var expected = (item.getAttribute("data-answer") || "").trim().toLowerCase();
  var answerEl = item.querySelector(".quiz-answer");
  if (!answerEl || expected === "") return;
  var given = (answerEl.textContent || "").trim().toLowerCase();
  item.classList.add(given === expected ? "correct" : "incorrect");
  var badge = document.createElement("div");
  badge.textContent = given === expected
    ? "\\u2713 correct"
    : "\\u2717 not quite \\u2014 reread and try again";
  item.appendChild(badge);
}});
</script>
</body>
</html>
"""

_NUMBERED_PAGE_RE = re.compile(r"^(\d+)-.*\.html$")

# Signature for the injected opener: opens a lesson page (default: the browser).
Opener = Callable[[Path], None]


def default_opener(page: Path) -> None:
    """Open a lesson page in the system's default browser."""
    webbrowser.open(str(page))


def render_lesson_page(topic: str, number: int, title: str, content: str) -> str:
    """Render a self-contained lesson page (inline CSS + quiz JS, no server)."""
    return _PAGE_TEMPLATE.format(
        topic=topic, number=number, title=title, content=content
    )


class LessonTool:
    """Write a self-contained HTML lesson page and open it in the browser.

    Lessons live under ``<working dir>/<LESSONS_DIR_NAME>/<topic-slug>/`` as
    numbered pages (``NN-slug.html``) plus an ``index.html`` linking them. Each
    page (and its quiz) is a single file — no server or build step.
    """

    name = "lesson"
    description = (
        "Write one self-contained HTML lesson page (explanations + a self-checking "
        "quiz) under the lessons directory and open it in the browser."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["topic", "content"],
    }

    def __init__(
        self,
        cwd: Path,
        opener: Opener | None = None,
    ) -> None:
        self._cwd = cwd
        self._opener: Opener = opener or default_opener

    async def run(self, arguments: dict) -> ToolOutcome:
        topic = arguments.get("topic", "")
        content = arguments.get("content", "")
        title = arguments.get("title") or topic
        if not topic:
            return ToolOutcome(content="error: lesson needs a topic", is_error=True)
        topic_slug = _slugify(topic)

        # _slugify strips every path separator, so this is always the direct
        # child of the lessons root — containment is guaranteed by construction.
        topic_dir = self._cwd / LESSONS_DIR_NAME / topic_slug

        try:
            topic_dir.mkdir(parents=True, exist_ok=True)
            number = self._next_number(topic_dir)
            page_path = topic_dir / f"{number:02d}-{_slugify(title)}.html"
            page_path.write_text(
                render_lesson_page(
                    topic=topic, number=number, title=title, content=content
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            return ToolOutcome(content=f"error: {exc}", is_error=True)

        self._write_index(topic_dir, topic)

        try:
            self._opener(page_path)
        except Exception:  # noqa: BLE001 - never fail the write over opening
            pass

        try:
            rel = page_path.relative_to(self._cwd)
        except ValueError:
            rel = page_path
        return ToolOutcome(content=f"wrote lesson '{topic}' → {rel}")

    def _next_number(self, topic_dir: Path) -> int:
        existing = 0
        for p in topic_dir.glob("*.html"):
            m = _NUMBERED_PAGE_RE.match(p.name)
            if m:
                existing = max(existing, int(m.group(1)))
        return existing + 1

    def _write_index(self, topic_dir: Path, topic: str) -> None:
        pages = sorted(p for p in topic_dir.glob("*.html") if p.name != "index.html")
        items = "\n".join(f'<li><a href="{p.name}">{p.name}</a></li>' for p in pages)
        (topic_dir / "index.html").write_text(
            '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f"<title>{topic} — lessons</title></head><body>"
            f"<h1>{topic}</h1><ol>\n{items}\n</ol></body></html>\n",
            encoding="utf-8",
        )


# ── strict-learn guard ──────────────────────────────────────────────────


class GuardedWriteTool(WriteTool):
    """A write tool that blocks any target outside the lessons directory."""

    async def run(self, arguments: dict) -> ToolOutcome:
        blocked = _blocked_if_outside(self._cwd, arguments.get("path", ""))
        if blocked is not None:
            return blocked
        return await super().run(arguments)


class GuardedEditTool(EditTool):
    """An edit tool that blocks any target outside the lessons directory."""

    async def run(self, arguments: dict) -> ToolOutcome:
        blocked = _blocked_if_outside(self._cwd, arguments.get("path", ""))
        if blocked is not None:
            return blocked
        return await super().run(arguments)
