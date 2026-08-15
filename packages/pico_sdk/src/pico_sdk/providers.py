"""Provider construction from settings and the environment."""

from __future__ import annotations

import os

from pico_ai.openrouter import OpenRouterProvider

from .config import Settings, load_settings


def create_provider(settings: Settings | None = None) -> OpenRouterProvider:
    """Build the default OpenRouter provider from the configured API key env var."""
    settings = settings or load_settings()
    api_key = os.environ.get(settings.api_key_env, "")
    return OpenRouterProvider(api_key=api_key)
