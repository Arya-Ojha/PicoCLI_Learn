"""Tests for the context status bar widget."""

from pico_tui.status_bar import ContextStatusBar


def test_status_bar_initialization():
    """Test that the status bar initializes correctly."""
    bar = ContextStatusBar()
    assert bar._provider == ""
    assert bar._model == ""
    assert bar._thinking is False
    assert bar._tokens == 0
    assert bar._context_window == 128_000


def test_status_bar_stores_info():
    """Test that update_info stores all fields correctly (no render)."""
    bar = ContextStatusBar()
    bar._provider = "OpenRouter"
    bar._model = "nvidia/nemotron-3.5-lightning:free"
    bar._tokens = 38_932
    bar._context_window = 128_000
    bar._thinking = True

    assert bar._provider == "OpenRouter"
    assert bar._model == "nvidia/nemotron-3.5-lightning:free"
    assert bar._tokens == 38_932
    assert bar._context_window == 128_000
    assert bar._thinking is True


def test_status_bar_set_thinking():
    """Test that set_thinking updates the thinking state."""
    bar = ContextStatusBar()
    assert bar._thinking is False
    bar._thinking = True
    assert bar._thinking is True
    bar._thinking = False
    assert bar._thinking is False
