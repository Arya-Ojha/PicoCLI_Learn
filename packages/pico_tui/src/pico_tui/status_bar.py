"""Context status bar widget for the TUI."""

from __future__ import annotations

from textual.widgets import Static
from rich.text import Text


class ContextStatusBar(Static):
    """A status bar showing provider, model, thinking state, and context usage."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._provider = ""
        self._model = ""
        self._thinking = False
        self._tokens = 0
        self._context_window = 128_000

    def on_mount(self) -> None:
        """Render the initial display after the widget is mounted."""
        # Set initial placeholder content
        self._provider = "OpenRouter"
        self._model = "nemotron-3.5-lightning:free"
        self._tokens = 0
        self._context_window = 128000
        self._update_display()

    def update_info(
        self,
        provider: str,
        model: str,
        tokens: int,
        context_window: int,
        thinking: bool = False,
    ) -> None:
        """Update the status bar with new information."""
        self._provider = provider
        self._model = model
        self._tokens = tokens
        self._context_window = context_window
        self._thinking = thinking
        self._update_display()

    def set_thinking(self, thinking: bool) -> None:
        """Update the thinking state."""
        self._thinking = thinking
        self._update_display()

    def _update_display(self) -> None:
        """Render the status bar."""
        # If no provider/model set yet, show placeholder
        provider = self._provider or "no-provider"
        model = self._model or "no-model"
        
        # Provider and model
        info = Text(f"{provider} | {model}")

        # Thinking indicator
        if self._thinking:
            info.append(" | ")
            info.append("thinking", style="bold yellow")

        # Context window bar
        bar_width = 20
        fill_ratio = min(self._tokens / self._context_window, 1.0) if self._context_window > 0 else 0.0
        filled = int(bar_width * fill_ratio)

        info.append(" | [")

        # Build the progress bar
        bar = ""
        for i in range(bar_width):
            if i < filled:
                # Character based on usage percentage
                if fill_ratio > 0.9:
                    bar += "█"
                elif fill_ratio > 0.7:
                    bar += "▓"
                elif fill_ratio > 0.5:
                    bar += "▒"
                else:
                    bar += "░"
            else:
                bar += " "

        # Add color based on usage level
        if fill_ratio > 0.9:
            info.append(bar, style="bold red")
        elif fill_ratio > 0.7:
            info.append(bar, style="bold yellow")
        else:
            info.append(bar, style="bold green")

        info.append("]")

        # Token count (formatted with commas)
        token_str = f"{self._tokens:,}"
        info.append(f" {token_str}", style="bold cyan")

        self.update(info)
