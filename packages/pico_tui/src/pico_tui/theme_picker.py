"""Modal theme-picker screen for the TUI (/theme with no argument)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, OptionList


def theme_options(current: str = "") -> list[str]:
    """Return the picker list: curated suggestions, current first if exotic."""
    from .render import THEME_SUGGESTIONS

    options = list(THEME_SUGGESTIONS)
    if current and current not in options:
        options.insert(0, current)
    return options


def format_theme_option(name: str, current: str = "") -> str:
    """Return the display prompt for one theme entry."""
    marker = " [cyan]\u2713 current[/]" if name == current else ""
    return f"{name}{marker}"


class ThemePickerScreen(ModalScreen[str | None]):
    """A modal screen listing code themes; dismisses with the chosen name."""

    CSS = """
    ThemePickerScreen {
        align: center middle;
        background: $background 60%;
    }
    #theme-picker-dialog {
        width: 60%;
        max-width: 60;
        height: 50%;
        border: round $primary;
        background: $surface;
        padding: 0 1;
    }
    #theme-picker-list {
        height: 1fr;
        border: none;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel", show=False),
    ]

    def __init__(self, themes: list[str], current: str = "") -> None:
        super().__init__()
        self._themes = themes
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-picker-dialog"):
            option_list = OptionList(id="theme-picker-list")
            for name in self._themes:
                option_list.add_option(format_theme_option(name, self._current))
            option_list.highlighted = 0
            yield option_list
        yield Footer()

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Dismiss with the selected theme name."""
        # Textual renamed the index attribute across versions.
        index: int = getattr(event, "option_index", 0) or getattr(
            event, "index", 0
        )
        self.dismiss(self._themes[index])

    def action_cancel(self) -> None:
        """Dismiss without changing the theme."""
        self.dismiss(None)
