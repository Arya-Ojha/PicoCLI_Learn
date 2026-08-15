"""Settings loaded from ``~/.pico/settings.json`` with sensible defaults."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """User-configurable settings for the agent."""

    model: str = "openrouter/auto"
    context_window: int = 128_000
    reserve_tokens: int = 16_384
    session_dir: str = "~/.pico/sessions"
    api_key_env: str = "OPENROUTER_API_KEY"


def default_settings_path() -> Path:
    """Return the default settings file path."""
    return Path.home() / ".pico" / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    """Load settings from ``path`` (default ``~/.pico/settings.json``).

    Missing keys fall back to defaults; a missing file yields all defaults.
    """
    path = Path(path) if path is not None else default_settings_path()
    if not path.exists():
        return Settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Settings.model_validate(data)
