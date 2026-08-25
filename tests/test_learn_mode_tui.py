"""Bonus seam — live Textual pilot test for the Tab mode toggle.

Presses Tab with the Input focused, asserts the footer reflects the flipped
mode, presses Tab again, and confirms it flips back. Uses a scripted
FakeProvider so no network is touched.
"""

from textual.widgets._footer import FooterKey

from pico_tui.app import PicoApp, _SessionManager

from conftest import FakeProvider, make_session


def _make_app(tmp_path) -> PicoApp:
    provider = FakeProvider([])  # never called: we only toggle the mode
    session = make_session(provider, tmp_path)
    return PicoApp(_SessionManager(session))


def _badge(app: PicoApp) -> list[str]:
    """The key_display of every FooterKey bound to toggle_learn."""
    return [
        key.key_display
        for key in app.query(FooterKey)
        if key.action == "toggle_learn"
    ]


async def test_tab_toggles_mode_and_updates_footer(tmp_path):
    app = _make_app(tmp_path)
    async with app.run_test() as pilot:
        assert app._mode == "act"

        await pilot.press("tab")
        await pilot.pause()
        assert app._mode == "learn"
        assert _badge(app) == ["[learn]"]

        await pilot.press("tab")
        await pilot.pause()
        assert app._mode == "act"
        assert _badge(app) == ["[act]"]
