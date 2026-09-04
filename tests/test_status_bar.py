"""Smoke: status bar init."""

from pico_tui.status_bar import ContextStatusBar


def test_status_bar_initialization():
    bar = ContextStatusBar()
    assert bar._provider == ""
    assert bar._model == ""
    assert bar._thinking is False
    assert bar._tokens == 0
    assert bar._context_window == 128_000
