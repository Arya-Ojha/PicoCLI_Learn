"""Smoke: TUI command parsing + text rendering."""

from rich.console import Console

from pico_core.fsm import LoopEvent
from pico_tui.commands import Command, parse_line
from pico_tui.render import render_event

_console = Console(force_terminal=True, color_system=None, width=200, height=100)


def _render_text(event: LoopEvent) -> str:
    rendered = render_event(event)
    if rendered is None:
        return ""
    with _console.capture() as capture:
        _console.print(rendered)
    return capture.get().rstrip()


def test_parse_line_commands():
    assert parse_line("/quit") == Command("quit")
    assert parse_line("/help") == Command("help")
    assert parse_line("/history") == Command("history")
    assert parse_line("/undo") == Command("undo")
    assert parse_line("/compact focus on the bug") == Command("compact", "focus on the bug")
    assert parse_line("/fork abc123") == Command("fork", "abc123")
    assert parse_line("/provider") == Command("provider", "")
    assert parse_line("/provider local") == Command("provider", "local")
    assert parse_line("/provider openrouter") == Command("provider", "openrouter")


def test_render_event_text():
    event = LoopEvent(kind="text", text="hi")
    assert _render_text(event) == "hi"


def test_render_event_markdown_has_no_raw_stars():
    event = LoopEvent(kind="text", text="There are **3 files** and **2 directories**")
    assert "**" not in _render_text(event)
    assert "3 files" in _render_text(event)


def test_thinking_line_is_single_click_target():
    from pico_tui.app import PicoApp, ThinkingSegment, _SessionManager

    class _FakeSession:
        pass

    app = PicoApp(_SessionManager(_FakeSession()))  # type: ignore[arg-type]
    seg = ThinkingSegment(text="line one\nline two", id=1, final=True)
    collapsed = app._thinking_renderable(seg)
    assert isinstance(collapsed, str)
    assert collapsed.startswith("[@click=app.toggle_thinking(1)]")
    assert "line one" in collapsed
    assert "line two" not in collapsed
    assert collapsed.rstrip().endswith("...[/][/]")
    # Clicking anywhere expands; the expanded block collapses on any click too.
    app._thinking_expanded.add(1)
    expanded = app._thinking_renderable(seg)
    assert isinstance(expanded, str)
    assert expanded.startswith("[@click=app.toggle_thinking(1)]")
    assert "line two" in expanded


def test_single_line_thinking_is_not_clickable():
    from rich.text import Text

    from pico_tui.app import PicoApp, ThinkingSegment, _SessionManager

    class _FakeSession:
        pass

    app = PicoApp(_SessionManager(_FakeSession()))  # type: ignore[arg-type]
    seg = ThinkingSegment(text="just one line", id=2, final=True)
    rendered = app._thinking_renderable(seg)
    assert isinstance(rendered, Text)
    assert rendered.plain == "💭 just one line"
    assert "@click" not in rendered.plain
    assert "..." not in rendered.plain


def test_render_bash_result_hides_output():
    from pico_core.session import ToolResultPayload

    ok = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c1", name="bash", content="secret output\n[exit code: 0]"
        ),
    )
    rendered = _render_text(ok)
    assert "secret output" not in rendered
    assert "passed" in rendered

    err = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c2", name="bash", content="boom\n[exit code: 1]", is_error=True
        ),
    )
    assert "error" in _render_text(err)


async def test_provider_shows_current(tmp_path):
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    mgr = _SessionManager(make_session(FakeProvider([]), tmp_path))
    msg, changed = await mgr.provider("")
    assert changed is False
    assert "local" in msg


async def test_provider_switch_to_local_autodetects(monkeypatch, tmp_path):
    import pico_tui.app as app_module
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    class _LocalStub:
        async def list_models(self):
            return [{"id": "tiny-llama", "name": "tiny"}]

    monkeypatch.setattr(app_module, "create_provider", lambda settings: _LocalStub())
    session = make_session(FakeProvider([]), tmp_path)
    msg, changed = await _SessionManager(session).provider("local")
    assert changed is True
    assert session.model == "tiny-llama"
    assert session.loop.provider.__class__ is _LocalStub
    assert "local" in msg


async def test_provider_openrouter_needs_key(monkeypatch, tmp_path):
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    session = make_session(FakeProvider([]), tmp_path)
    before = session.loop.provider
    msg, changed = await _SessionManager(session).provider("openrouter")
    assert changed is False
    assert "not set" in msg
    assert session.loop.provider is before


async def test_provider_openrouter_resolves_free(monkeypatch, tmp_path):
    import pico_tui.app as app_module
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    class _OpenRouterStub:
        async def list_models(self):
            return [
                {"id": "z/free", "name": "Z Free", "is_free": True, "supports_tools": True}
            ]

    monkeypatch.setattr(app_module, "create_provider", lambda settings: _OpenRouterStub())
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    session = make_session(FakeProvider([]), tmp_path)
    msg, changed = await _SessionManager(session).provider("openrouter")
    assert changed is True
    assert session.model == "z/free"


def test_bash_error_segment_collapses_and_expands():
    from pico_tui.app import BashResultSegment, PicoApp, _SessionManager

    class _FakeSession:
        pass

    app = PicoApp(_SessionManager(_FakeSession()))  # type: ignore[arg-type]
    seg = BashResultSegment(content="boom\n[exit code: 1]", is_error=True, id=1)
    collapsed = app._bash_renderable(seg)
    assert isinstance(collapsed, str)
    assert collapsed.startswith("[@click=app.toggle_bash(1)]")
    assert "boom" not in collapsed
    assert "error" in collapsed
    app._bash_expanded.add(1)
    expanded = app._bash_renderable(seg)
    assert isinstance(expanded, str)
    assert "boom" in expanded


async def test_manager_emits_segment_for_failed_bash_only():
    from rich.panel import Panel

    from pico_core.session import ToolResultPayload
    from pico_tui.app import BashResultSegment, _SessionManager

    class _StubSession:
        def __init__(self, events):
            self._events = events

        async def stream(self, prompt):
            for event in self._events:
                yield event

    failed = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c1", name="bash", content="boom\n[exit code: 1]", is_error=True
        ),
    )
    passed = LoopEvent(
        kind="tool_result",
        tool_result=ToolResultPayload(
            tool_call_id="c2", name="bash", content="hi\n[exit code: 0]"
        ),
    )
    captured: list = []
    await _SessionManager(_StubSession([failed, passed])).stream(  # type: ignore[arg-type]
        "hi", captured.append
    )
    assert isinstance(captured[0], BashResultSegment)
    assert isinstance(captured[1], Panel)
