"""Smoke: TUI command parsing + text rendering."""

from rich.console import Console

from pico_core.fsm import LoopEvent
from pico_tui.commands import Command, Prompt, parse_line
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
    assert parse_line("/local") == Command("local", "")
    assert parse_line("/local http://127.0.0.1:11434") == Command(
        "local", "http://127.0.0.1:11434"
    )
    assert parse_line("/local vision http://127.0.0.1:11434") == Command(
        "local", "vision http://127.0.0.1:11434"
    )
    # No /theme command: theme switching lives in the Ctrl+P palette.
    assert parse_line("/theme dracula") == Prompt("/theme dracula")


def test_render_event_text():
    event = LoopEvent(kind="text", text="hi")
    assert _render_text(event) == "hi"


def test_render_event_markdown_has_no_raw_stars():
    event = LoopEvent(kind="text", text="There are **3 files** and **2 directories**")
    assert "**" not in _render_text(event)
    assert "3 files" in _render_text(event)


def test_todo_write_request_is_hidden():
    from pico_core.session import ToolRequestPayload
    from pico_ai.types import ToolCall

    event = LoopEvent(
        kind="tool_request",
        tool_request=ToolRequestPayload(
            tool_call=ToolCall(
                id="c1",
                name="todo_write",
                arguments={"todos": [{"content": "x", "status": "pending"}]},
            )
        ),
    )
    assert render_event(event) is None


def _request_event(name: str, arguments: dict) -> LoopEvent:
    from pico_ai.types import ToolCall
    from pico_core.session import ToolRequestPayload

    return LoopEvent(
        kind="tool_request",
        tool_request=ToolRequestPayload(
            tool_call=ToolCall(id="c1", name=name, arguments=arguments)
        ),
    )


def test_edit_request_renders_red_green_diff():
    from rich.syntax import Syntax

    event = _request_event(
        "edit", {"path": "a.py", "old_text": "x = 1", "new_text": "x = 2"}
    )
    text = _render_text(event)
    assert "- x = 1" in text
    assert "+ x = 2" in text
    parts = render_event(event)._renderables
    blocks = [p for p in parts if isinstance(p, Syntax)]
    assert blocks  # code stays syntax-highlighted, not plain text
    red = [b for b in blocks if b.background_color == "#3a1c1c"]
    green = [b for b in blocks if b.background_color == "#1c3a22"]
    assert any("- x = 1" in b.code for b in red)
    assert any("+ x = 2" in b.code for b in green)


def test_write_request_renders_all_green():
    from rich.syntax import Syntax

    event = _request_event("write", {"path": "b.py", "content": "y = 3"})
    text = _render_text(event)
    assert "+ y = 3" in text
    assert "- y = 3" not in text
    parts = render_event(event)._renderables
    blocks = [p for p in parts if isinstance(p, Syntax)]
    assert blocks
    assert all(b.background_color == "#1c3a22" for b in blocks)


def test_read_write_edit_have_no_border_or_result():
    from rich.panel import Panel
    from rich.text import Text

    from pico_core.session import ToolResultPayload

    read_req = _request_event("read", {"path": "a.py"})
    rendered = render_event(read_req)
    assert isinstance(rendered, Text)
    assert not isinstance(rendered, Panel)
    assert "a.py" in rendered.plain

    edit_req = _request_event(
        "edit", {"path": "a.py", "old_text": "x = 1", "new_text": "x = 2"}
    )
    assert not isinstance(render_event(edit_req), Panel)

    for name in ("read", "write", "edit"):
        result = LoopEvent(
            kind="tool_result",
            tool_result=ToolResultPayload(
                tool_call_id="c1", name=name, content=f"{name} receipt"
            ),
        )
        assert render_event(result) is None


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


def test_theme_switch_show_and_reject(tmp_path, monkeypatch):
    from conftest import FakeProvider, make_session
    from pico_tui import render as render_module
    from pico_tui.app import _SessionManager

    monkeypatch.setattr(render_module, "CODE_THEME", "monokai")
    mgr = _SessionManager(make_session(FakeProvider([]), tmp_path))
    assert "monokai" in mgr.theme("")
    assert mgr.theme("dracula") == "switched to theme: dracula"
    assert render_module.CODE_THEME == "dracula"
    assert mgr.session.settings.code_theme == "dracula"
    assert mgr.theme("not-a-theme").startswith("error:")
    assert render_module.CODE_THEME == "dracula"  # unchanged on bad name


def test_set_code_theme_validation(monkeypatch):
    from pico_tui import render as render_module

    monkeypatch.setattr(render_module, "CODE_THEME", "monokai")
    assert render_module.set_code_theme("dracula") is True
    assert render_module.CODE_THEME == "dracula"
    assert render_module.set_code_theme("bogus") is False
    assert render_module.CODE_THEME == "dracula"


async def test_theme_choice_persists(tmp_path, monkeypatch):
    import pico_tui.app as app_module
    from conftest import FakeProvider, make_session
    from pico_tui.app import PicoApp, _SessionManager

    saved: dict = {}
    monkeypatch.setattr(
        app_module, "save_settings", lambda s: saved.update(s.model_dump())
    )
    app = PicoApp(_SessionManager(make_session(FakeProvider([]), tmp_path)))
    async with app.run_test():
        app._apply_theme_choice("dracula")
        assert saved.get("code_theme") == "dracula"
        app._apply_theme_choice(None)  # cancel: nothing more saved
        assert saved.get("code_theme") == "dracula"


def test_theme_options_marks_current_first_if_exotic():
    from pico_tui.theme_picker import format_theme_option, theme_options

    options = theme_options("monokai")
    assert "monokai" in options
    assert "dracula" in options
    assert theme_options("nord-light") == ["nord-light", *theme_options("monokai")]
    assert format_theme_option("dracula", "dracula").endswith("current[/]")
    assert "current" not in format_theme_option("dracula", "monokai")


async def test_theme_picker_selects_highlighted(tmp_path):
    from conftest import FakeProvider, make_session
    from pico_tui.app import PicoApp, _SessionManager
    from pico_tui.theme_picker import ThemePickerScreen

    app = PicoApp(_SessionManager(make_session(FakeProvider([]), tmp_path)))
    chosen: list = []
    async with app.run_test() as pilot:
        app.push_screen(
            ThemePickerScreen(["monokai", "dracula"], current="monokai"),
            callback=chosen.append,
        )
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert chosen == ["monokai"]


async def test_app_theme_restores_saved(tmp_path):
    from conftest import FakeProvider, make_session
    from pico_tui.app import PicoApp, _SessionManager

    session = make_session(FakeProvider([]), tmp_path)
    session.settings.app_theme = "dracula"
    app = PicoApp(_SessionManager(session))
    async with app.run_test():
        assert app.theme == "dracula"


async def test_app_theme_change_persists(tmp_path):
    from conftest import FakeProvider, make_session
    from pico_sdk.config import load_settings
    from pico_tui.app import PicoApp, _SessionManager

    app = PicoApp(_SessionManager(make_session(FakeProvider([]), tmp_path)))
    async with app.run_test() as pilot:
        assert app.theme == "textual-dark"
        app.theme = "monokai"
        await pilot.pause()
        assert load_settings().app_theme == "monokai"


async def test_app_theme_unknown_falls_back(tmp_path):
    from conftest import FakeProvider, make_session
    from pico_tui.app import PicoApp, _SessionManager

    session = make_session(FakeProvider([]), tmp_path)
    session.settings.app_theme = "bogus-nope"
    app = PicoApp(_SessionManager(session))
    async with app.run_test():
        assert app.theme == "textual-dark"


async def test_write_log_indents_and_separates_segments(tmp_path):
    from conftest import FakeProvider, make_session
    from rich.text import Text
    from textual.widgets import RichLog

    from pico_tui.app import PicoApp

    app = PicoApp(make_session(FakeProvider([]), tmp_path))
    async with app.run_test():
        app._write_log(Text("hello"))
        app._write_log("[@click=app.toggle_bash(1)][red]bash error...[/][/]")
        log = app.query_one("#chat-log", RichLog)
        body = "\n".join(strip.text for strip in log.lines)
        assert "  hello" in body  # left-indented renderable
        # Markup still parsed (click target intact), visible text indented.
        assert "  bash error..." in body
        assert "[@click" not in body
        assert body.count("\n\n") >= 2  # blank line after each segment


async def test_local_shows_all_slots(tmp_path):
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    mgr = _SessionManager(make_session(FakeProvider([]), tmp_path))
    msg, changed = await mgr.local("")
    assert changed is False
    assert "orchestrator" in msg and "vision" in msg and "summary" in msg


async def test_local_sets_orchestrator_directly(monkeypatch, tmp_path):
    import pico_tui.app as app_module
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    class _LocalStub:
        def __init__(self, *args, **kwargs):
            pass

        async def list_models(self):
            return [{"id": "coder", "name": "coder"}]

    monkeypatch.setattr(app_module, "create_provider", lambda settings: _LocalStub())

    async def _resolve(provider, settings):
        return "coder", [{"id": "coder", "name": "coder"}]

    monkeypatch.setattr(app_module, "resolve_model", _resolve)
    session = make_session(FakeProvider([]), tmp_path)
    msg, changed = await _SessionManager(session).local("127.0.0.1:8000")
    assert changed is True
    assert session.settings.base_url == "http://127.0.0.1:8000/v1"
    assert session.model == "coder"
    assert "orchestrator endpoint set to" in msg


async def test_local_warns_on_nuextract_orchestrator(monkeypatch, tmp_path):
    import pico_tui.app as app_module
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    class _LocalStub:
        def __init__(self, *args, **kwargs):
            pass

        async def list_models(self):
            return [{"id": "nuextract-3", "name": "nuextract-3"}]

    monkeypatch.setattr(app_module, "create_provider", lambda settings: _LocalStub())

    async def _resolve(provider, settings):
        return "nuextract-3", [{"id": "nuextract-3", "name": "nuextract-3"}]

    monkeypatch.setattr(app_module, "resolve_model", _resolve)
    session = make_session(FakeProvider([]), tmp_path)
    msg, changed = await _SessionManager(session).local("http://127.0.0.1:11434")
    assert changed is True
    assert "extraction-only" in msg


async def test_local_vision_slot_and_clear(monkeypatch, tmp_path):
    import pico_sdk.providers as providers_module
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    async def _slot(base_url, model):
        return "vis", [{"id": "vis", "name": "vis"}], "ok"

    monkeypatch.setattr(providers_module, "resolve_slot", _slot)
    session = make_session(FakeProvider([]), tmp_path)
    mgr = _SessionManager(session)
    msg, changed = await mgr.local("vision 127.0.0.1:11434")
    assert changed is True
    assert session.settings.vision_base_url == "http://127.0.0.1:11434/v1"
    assert session.settings.vision_model == "vis"
    assert msg.startswith("vision slot set to")
    msg, changed = await mgr.local("vision")
    assert changed is True
    assert session.settings.vision_base_url == ""
    assert "cleared" in msg


async def test_local_rejects_bad_url_without_mutating(tmp_path):
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    session = make_session(FakeProvider([]), tmp_path)
    before = session.settings.base_url
    msg, changed = await _SessionManager(session).local("http://")
    assert changed is False and msg.startswith("error:")
    assert session.settings.base_url == before


async def test_apply_local_slots_validates_first(monkeypatch, tmp_path):
    import pico_tui.app as app_module
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    session = make_session(FakeProvider([]), tmp_path)
    mgr = _SessionManager(session)
    before_url = session.settings.base_url
    msg, changed = await mgr.apply_local_slots(
        {"orchestrator_model": "", "orchestrator_url": "http://localhost:8000",
         "vision_model": "", "vision_url": "http://",
         "summary_model": "", "summary_url": ""}
    )
    assert changed is False and msg.startswith("error in vision slot")
    assert session.settings.base_url == before_url
    assert session.settings.vision_base_url == ""


async def test_apply_local_slots_popup_values(monkeypatch, tmp_path):
    import pico_sdk.providers as providers_module
    import pico_tui.app as app_module
    from conftest import FakeProvider, make_session
    from pico_tui.app import _SessionManager

    class _LocalStub:
        def __init__(self, *args, **kwargs):
            pass

        async def list_models(self):
            return [{"id": "coder", "name": "coder"}]

    monkeypatch.setattr(app_module, "create_provider", lambda settings: _LocalStub())

    async def _resolve(provider, settings):
        return "coder", [{"id": "coder", "name": "coder"}]

    monkeypatch.setattr(app_module, "resolve_model", _resolve)

    async def _slot(base_url, model):
        return "vis", [{"id": "vis", "name": "vis"}], "ok"

    monkeypatch.setattr(providers_module, "resolve_slot", _slot)
    session = make_session(FakeProvider([]), tmp_path)
    msg, changed = await _SessionManager(session).apply_local_slots(
        {"orchestrator_model": "", "orchestrator_url": "localhost:8000",
         "vision_model": "", "vision_url": "127.0.0.1:11434",
         "summary_model": "tiny", "summary_url": ""}
    )
    assert changed is True
    assert session.settings.base_url == "http://localhost:8000/v1"
    assert session.settings.vision_base_url == "http://127.0.0.1:11434/v1"
    assert session.settings.vision_model == "vis"
    assert session.settings.summary_base_url == ""
    assert session.settings.summary_model == "tiny"
    assert "orchestrator:" in msg and "vision:" in msg and "summary:" in msg


async def test_local_popup_saves_and_cancels(tmp_path):
    from conftest import FakeProvider, make_session
    from pico_tui.app import PicoApp, _SessionManager
    from pico_tui.local_screen import LocalEndpointScreen

    app = PicoApp(_SessionManager(make_session(FakeProvider([]), tmp_path)))
    chosen: list = []
    async with app.run_test() as pilot:
        from textual.widgets import Button

        app.push_screen(
            LocalEndpointScreen(
                orchestrator_model="",
                orchestrator_url="http://localhost:8000/v1",
                vision_model="",
                vision_url="",
                summary_model="",
                summary_url="",
            ),
            callback=chosen.append,
        )
        await pilot.pause()
        app.screen.query_one("#local-save", Button).focus()
        await pilot.press("enter")
        await pilot.pause()
    assert len(chosen) == 1
    assert chosen[0]["orchestrator_url"] == "http://localhost:8000/v1"

    cancelled: list = []
    app2 = PicoApp(_SessionManager(make_session(FakeProvider([]), tmp_path)))
    async with app2.run_test() as pilot:
        from textual.widgets import Button

        app2.push_screen(LocalEndpointScreen(), callback=cancelled.append)
        await pilot.pause()
        app2.screen.query_one("#local-cancel", Button).focus()
        await pilot.press("enter")
        await pilot.pause()
    assert cancelled == [None]
