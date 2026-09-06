"""Modal local-endpoint screen for the TUI (/local with no argument)."""

from __future__ import annotations

from pico_ai.local import normalize_base_url

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label

__all__ = ["normalize_base_url", "LocalEndpointScreen"]


class LocalEndpointScreen(ModalScreen[str | None]):
    """A modal dialog with an endpoint input; dismisses with the raw value."""

    CSS = """
    LocalEndpointScreen {
        align: center middle;
        background: $background 60%;
    }
    #local-endpoint-dialog {
        width: 80%;
        max-width: 80;
        height: auto;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }
    #local-endpoint-input {
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, current: str = "") -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="local-endpoint-dialog"):
            yield Label(f"Local server endpoint (current: {self._current or 'unset'})")
            yield Label("e.g. http://127.0.0.1:11434  or  http://localhost:8000/v1")
            yield Input(
                id="local-endpoint-input",
                placeholder="http://127.0.0.1:11434",
                value=self._current,
            )
            with Horizontal():
                yield Button("Save", id="local-save", variant="primary")
                yield Button("Cancel", id="local-cancel")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismiss with the input value on Save, or None on Cancel."""
        if event.button.id == "local-cancel":
            self.dismiss(None)
            return
        if event.button.id == "local-save":
            value = self.query_one("#local-endpoint-input", Input).value
            self.dismiss(value)

    def action_cancel(self) -> None:
        """Dismiss without changing the endpoint."""
        self.dismiss(None)
