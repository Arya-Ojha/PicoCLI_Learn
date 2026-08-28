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


FREE_MODEL_ALIAS = "openrouter/free"


async def resolve_free_model(provider: OpenRouterProvider) -> str | None:
    """Resolve the ``openrouter/free`` alias to a concrete free model id.

    Picks the first free model (alphabetically) that supports tool calling;
    falls back to any free model. Returns None if nothing free is available
    or the lookup fails — callers should keep the alias as-is in that case.
    """
    try:
        models = await provider.list_models()
    except Exception:
        return None
    free = sorted(
        (m for m in models if m["is_free"]),
        key=lambda m: m["name"].lower(),
    )
    with_tools = [m for m in free if m.get("supports_tools")]
    if with_tools:
        return with_tools[0]["id"]
    return free[0]["id"] if free else None
