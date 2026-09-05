"""Settings loaded from ``~/.pico/settings.json`` with sensible defaults."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """User-configurable settings for the agent."""

    # Which backend serves the model: "local" (loopback vLLM server,
    # air-tight) or "openrouter" (cloud; kept for testing, slated for
    # removal in the final version).
    provider: str = "local"
    # Base URL of the local OpenAI-compatible server (vLLM default).
    base_url: str = "http://localhost:8000/v1"
    # Model id, or "" for auto-detect: the served model is picked from the
    # local server (single served model is used directly; with several,
    # the first is used and /model offers the rest as a selector).
    model: str = ""
    models_file: str = "~/.pico/models.yaml"
    context_window: int = 128_000
    reserve_tokens: int = 16_384
    session_dir: str = "~/.pico/sessions"
    # Only used by the "openrouter" provider.
    api_key_env: str = "OPENROUTER_API_KEY"
    # Optional: env var holding the local server key, only if the server
    # was started with --api-key. Empty means no auth header is sent.
    local_api_key_env: str = "VLLM_API_KEY"
    # Pygments theme for code blocks in the TUI (e.g. monokai, dracula,
    # github-dark). Any style pygments ships is accepted.
    code_theme: str = "monokai"
    # Textual app theme for the TUI (e.g. textual-dark, dracula, nord).
    # Set from the Ctrl+P command palette; restored on launch.
    app_theme: str = "textual-dark"


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


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    """Persist ``settings`` to ``path`` (default ``~/.pico/settings.json``)."""
    path = Path(path) if path is not None else default_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings.model_dump(), indent=2) + "\n", encoding="utf-8"
    )
    return path
