"""Provider construction from settings and the environment."""

from __future__ import annotations

import os
from typing import Any

from pico_ai.local import DEFAULT_LOCAL_BASE_URL, LocalProvider
from pico_ai.openrouter import OpenRouterProvider

from .config import Settings, load_settings

#: Default model when nothing is configured and auto-detect finds nothing
#: to pick from (e.g. the local server is unreachable at startup and the
#: user proceeds anyway). Callers should prefer auto-detect.
FALLBACK_MODEL = "qwen2.5-coder:32b"


def create_provider(settings: Settings | None = None) -> Any:
    """Build the configured provider.

    ``"local"`` (default) serves from the loopback vLLM server — fully
    air-tight, no API key needed. ``"openrouter"`` is the cloud backend,
    kept for testing and slated for removal in the final version.
    """
    settings = settings or load_settings()
    if (settings.provider or "local").lower() == "openrouter":
        api_key = os.environ.get(settings.api_key_env, "")
        return OpenRouterProvider(api_key=api_key)
    api_key = ""
    if settings.local_api_key_env:
        api_key = os.environ.get(settings.local_api_key_env, "")
    return LocalProvider(
        base_url=settings.base_url or DEFAULT_LOCAL_BASE_URL,
        api_key=api_key,
    )


async def resolve_model(
    provider: Any, settings: Settings
) -> tuple[str, list[dict]]:
    """Pick the model id to run with, auto-detecting served models.

    Returns ``(model_id, served)`` where ``served`` is the full served
    list (empty when the lookup failed). Rules:

    - If ``settings.model`` names a served model, it wins (covers stale
      configs like the old ``openrouter/free`` alias: unknown ids fall
      through to auto-detect).
    - One served model → use it.
    - Several → the first; the caller tells the user about ``/model``.
    - Lookup failure / empty → the configured model, or FALLBACK_MODEL.
    """
    served: list[dict] = []
    list_models = getattr(provider, "list_models", None)
    if callable(list_models):
        try:
            served = await list_models()
        except Exception:
            served = []
    ids = [m.get("id", "") for m in served if m.get("id")]
    configured = (settings.model or "").strip()
    if configured and configured in ids:
        return configured, served
    if len(ids) == 1:
        return ids[0], served
    if ids:
        return ids[0], served
    return configured or FALLBACK_MODEL, served


FREE_MODEL_ALIAS = "openrouter/free"


async def resolve_free_model(provider: Any) -> str | None:
    """Resolve the ``openrouter/free`` alias to a concrete free model id.

    OpenRouter-only (used when ``provider`` is ``"openrouter"``).
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
