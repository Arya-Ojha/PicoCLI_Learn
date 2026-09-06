"""Modal local-endpoint screen for the TUI (/local with no argument).

Three independent slots — coding/reasoning (orchestrator), vision
(extraction subagent), summary (fast small model) — each with a model id
and an endpoint URL. Slots may share one URL (a single capable server)
or point at different servers. Dismisses with a dict of raw values.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label

from pico_ai.local import normalize_base_url

__all__ = ["normalize_base_url", "LocalEndpointScreen", "SlotValues"]

#: The raw (unnormalized, unvalidated) values from the popup form.
SlotValues = dict[str, str]

_ORCH = "orchestrator"
_VISION = "vision"
_SUMMARY = "summary"


def _slot_fields(slot: str) -> tuple[str, str]:
    """Return the ``(model_input_id, url_input_id)`` for a slot."""
    return f"{slot}-model", f"{slot}-url"


class LocalEndpointScreen(ModalScreen[SlotValues | None]):
    """A modal dialog with three model+endpoint slots."""

    CSS = """
    LocalEndpointScreen {
        align: center middle;
        background: $background 60%;
    }
    #local-endpoint-dialog {
        width: 80%;
        max-width: 90;
        height: 90%;
        max-height: 100%;
        border: round $primary;
        background: $surface;
        padding: 1 2;
        overflow-y: auto;
    }
    #local-endpoint-dialog Input {
        width: 100%;
    }
    .slot-title {
        text-style: bold;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        orchestrator_model: str = "",
        orchestrator_url: str = "",
        vision_model: str = "",
        vision_url: str = "",
        summary_model: str = "",
        summary_url: str = "",
    ) -> None:
        super().__init__()
        self._initial = {
            _ORCH: (orchestrator_model, orchestrator_url),
            _VISION: (vision_model, vision_url),
            _SUMMARY: (summary_model, summary_url),
        }

    def compose(self) -> ComposeResult:
        with Vertical(id="local-endpoint-dialog"):
            yield Label("Local models — each slot has its own endpoint.")
            yield Label("Leave the orchestrator URL empty for OpenRouter (default); leave a vision/summary URL empty to share the orchestrator endpoint.", id="local-hint")
            for slot, title, hint in (
                (_ORCH, "Coding / reasoning (orchestrator — drives the agent)", "e.g. empty = OpenRouter default, or http://localhost:8000"),
                (_VISION, "Vision (extraction subagent — reads PDFs/images)", "e.g. http://127.0.0.1:11434"),
                (_SUMMARY, "Summary (fast small model — summaries, simple tasks)", "e.g. http://127.0.0.1:11434"),
            ):
                model, url = self._initial[slot]
                model_id, url_id = _slot_fields(slot)
                yield Label(title, classes="slot-title")
                yield Label(hint)
                yield Label("Model:")
                yield Input(id=model_id, placeholder="model id (empty = auto-detect / OpenRouter free)", value=model)
                yield Label("Endpoint URL:")
                yield Input(id=url_id, placeholder="empty = OpenRouter (orchestrator) or share orchestrator", value=url)
            with Horizontal():
                yield Button("Save", id="local-save", variant="primary")
                yield Button("Cancel", id="local-cancel")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismiss with the raw slot values on Save, or None on Cancel."""
        if event.button.id == "local-cancel":
            self.dismiss(None)
            return
        if event.button.id == "local-save":
            values: SlotValues = {}
            for slot in (_ORCH, _VISION, _SUMMARY):
                model_id, url_id = _slot_fields(slot)
                values[f"{slot}_model"] = self.query_one(f"#{model_id}", Input).value
                values[f"{slot}_url"] = self.query_one(f"#{url_id}", Input).value
            self.dismiss(values)

    def action_cancel(self) -> None:
        """Dismiss without changing anything."""
        self.dismiss(None)
