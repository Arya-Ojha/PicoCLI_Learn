"""Learn-mode tools — tool seam.

Prior art: tests/test_tools.py (plain async tests against tmp_path, ToolOutcome
asserts). All transports and openers are injected so tests never touch the
network or a real browser.
"""

from pico_core.learn_tools import (
    BLOCKED_IN_LEARN_MODE,
    FetchTool,
    GuardedEditTool,
    GuardedWriteTool,
    HttpResponse,
    LessonTool,
    SearchTool,
    is_within_lessons_dir,
    parse_duckduckgo_results,
)


# ── helpers ───────────────────────────────────────────────────────────


class _StubTransport:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def get(self, url):
        self.calls.append(url)
        return self._responses.pop(0)


class _RecorderOpener:
    def __init__(self):
        self.opened = []

    def __call__(self, path):
        self.opened.append(path)


# ── fetch ─────────────────────────────────────────────────────────────


async def test_fetch_returns_body():
    t = _StubTransport([HttpResponse(status=200, text="hello world")])
    out = await FetchTool(transport=t).run({"url": "https://x"})
    assert not out.is_error
    assert out.content == "hello world"


async def test_fetch_non_200_is_error():
    t = _StubTransport([HttpResponse(status=404, text="nope")])
    out = await FetchTool(transport=t).run({"url": "https://x"})
    assert out.is_error
    assert "404" in out.content


async def test_fetch_transport_failure_is_error():
    class Boom:
        async def get(self, url):
            raise RuntimeError("boom")

    out = await FetchTool(transport=Boom()).run({"url": "https://x"})
    assert out.is_error
    assert "boom" in out.content


# ── web search ────────────────────────────────────────────────────────

DDG_HTML = """
<html><body>
<a class="result__a" href="https://example.com/a">Alpha Title</a>
<a class="result__snippet" href="https://example.com/a">Snippet one</a>
<a class="result__a" href="https://example.com/b">Beta &amp; Title</a>
<a class="result__snippet" href="https://example.com/b">Snippet two</a>
</body></html>
"""


def test_parse_duckduckgo_results():
    results = parse_duckduckgo_results(DDG_HTML)
    assert len(results) == 2
    assert results[0]["title"] == "Alpha Title"
    assert results[0]["url"] == "https://example.com/a"
    assert "Snippet one" in results[0]["snippet"]
    assert results[1]["title"] == "Beta & Title"
    assert results[1]["url"] == "https://example.com/b"


async def test_search_uses_transport_and_parses():
    t = _StubTransport([HttpResponse(status=200, text=DDG_HTML)])
    out = await SearchTool(transport=t).run({"query": "react"})
    assert not out.is_error
    assert "Alpha Title" in out.content
    assert "https://example.com/a" in out.content
    assert t.calls
    assert "q=react" in t.calls[0]


async def test_search_no_results():
    t = _StubTransport([HttpResponse(status=200, text="<html></html>")])
    out = await SearchTool(transport=t).run({"query": "zzz"})
    assert "no results" in out.content.lower()


# ── lesson ────────────────────────────────────────────────────────────


async def test_lesson_creates_numbered_page_and_index(tmp_path):
    opener = _RecorderOpener()
    tool = LessonTool(tmp_path, opener=opener)
    out = await tool.run({"topic": "React JS", "content": "<p>hooks</p>"})
    assert not out.is_error
    topic_dir = tmp_path / "pico-lessons" / "react-js"
    page = topic_dir / "01-react-js.html"
    assert page.exists()
    html = page.read_text(encoding="utf-8")
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "React JS" in html
    assert "<p>hooks</p>" in html
    assert "<style>" in html and "<script>" in html
    index = topic_dir / "index.html"
    assert index.exists()
    assert "01-react-js.html" in index.read_text(encoding="utf-8")
    assert len(opener.opened) == 1


async def test_lesson_numbers_increment(tmp_path):
    opener = _RecorderOpener()
    tool = LessonTool(tmp_path, opener=opener)
    await tool.run({"topic": "react", "content": "a"})
    await tool.run({"topic": "react", "content": "b"})
    topic_dir = tmp_path / "pico-lessons" / "react"
    assert (topic_dir / "01-react.html").exists()
    assert (topic_dir / "02-react.html").exists()


async def test_lesson_never_escapes_working_dir(tmp_path):
    opener = _RecorderOpener()
    tool = LessonTool(tmp_path, opener=opener)
    out = await tool.run({"topic": "../../evil", "content": "x"})
    assert not out.is_error
    # Every generated HTML page must live inside the lessons directory.
    for page in tmp_path.rglob("*.html"):
        assert page.is_relative_to(tmp_path / "pico-lessons")


# ── path containment helper ───────────────────────────────────────────


def test_is_within_lessons_dir(tmp_path):
    assert is_within_lessons_dir(tmp_path, "pico-lessons/react/x.html")
    assert is_within_lessons_dir(tmp_path, "./pico-lessons/react/x.html")
    assert not is_within_lessons_dir(tmp_path, "src/foo.py")
    assert not is_within_lessons_dir(tmp_path, "../outside/x.html")


# ── strict-learn guard ────────────────────────────────────────────────


async def test_guarded_write_blocks_source_paths(tmp_path):
    out = await GuardedWriteTool(tmp_path).run(
        {"path": "src/foo.py", "content": "print(1)"}
    )
    assert out.is_error
    assert "blocked in learn mode" in out.content
    assert not (tmp_path / "src" / "foo.py").exists()


async def test_guarded_write_allows_lesson_paths(tmp_path):
    out = await GuardedWriteTool(tmp_path).run(
        {"path": "pico-lessons/react/01-react.html", "content": "<html>"}
    )
    assert not out.is_error
    assert (tmp_path / "pico-lessons" / "react" / "01-react.html").exists()


async def test_guarded_edit_blocks_source_paths(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    out = await GuardedEditTool(tmp_path).run(
        {"path": "a.py", "old_text": "x", "new_text": "y"}
    )
    assert out.is_error
    assert "blocked in learn mode" in out.content
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x"


async def test_guarded_edit_allows_lesson_paths(tmp_path):
    lesson = tmp_path / "pico-lessons" / "react" / "01-react.html"
    lesson.parent.mkdir(parents=True)
    lesson.write_text("abc", encoding="utf-8")
    out = await GuardedEditTool(tmp_path).run(
        {
            "path": "pico-lessons/react/01-react.html",
            "old_text": "abc",
            "new_text": "xyz",
        }
    )
    assert not out.is_error
    assert "xyz" in lesson.read_text(encoding="utf-8")
