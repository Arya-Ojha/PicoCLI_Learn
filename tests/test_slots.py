"""Slots: settings subagent pairs, slot fallback, and slot probing."""

import httpx

from pico_sdk.config import Settings
from pico_sdk.providers import resolve_slot


def test_slot_defaults_share_orchestrator():
    settings = Settings(model="big", base_url="http://localhost:8000/v1")
    assert settings.vision_model == "" and settings.vision_base_url == ""
    assert settings.summary_model == "" and settings.summary_base_url == ""
    assert settings.slot("vision") == ("big", "http://localhost:8000/v1")
    assert settings.slot("summary") == ("big", "http://localhost:8000/v1")


def test_slot_explicit_values_win():
    settings = Settings(
        model="big",
        base_url="http://localhost:8000/v1",
        vision_model="v",
        vision_base_url="http://127.0.0.1:11434/v1",
    )
    assert settings.slot("vision") == ("v", "http://127.0.0.1:11434/v1")
    assert settings.slot("summary") == ("big", "http://localhost:8000/v1")


async def test_resolve_slot_unreachable_keeps_values():
    import pico_sdk.providers as providers_module

    probe_calls: list = []

    class _Probe:
        def __init__(self, *args, **kwargs):
            pass

        async def list_models(self):
            probe_calls.append(1)
            raise httpx.ConnectError("down")

    # Patch LocalProvider used inside resolve_slot via the module namespace.
    orig = providers_module.LocalProvider
    providers_module.LocalProvider = _Probe  # type: ignore[assignment]
    try:
        model, served, note = await resolve_slot("http://127.0.0.1:11434/v1", "typed")
    finally:
        providers_module.LocalProvider = orig
    assert model == "typed" and served == []
    assert "unreachable" in note


async def test_resolve_slot_picks_single_served():
    import pico_sdk.providers as providers_module

    class _Probe:
        def __init__(self, *args, **kwargs):
            pass

        async def list_models(self):
            return [{"id": "small", "name": "small"}]

    orig = providers_module.LocalProvider
    providers_module.LocalProvider = _Probe  # type: ignore[assignment]
    try:
        model, served, note = await resolve_slot("http://x/v1", "")
    finally:
        providers_module.LocalProvider = orig
    assert model == "small" and len(served) == 1 and note.startswith("ok:")


async def test_resolve_slot_keeps_configured_when_served():
    import pico_sdk.providers as providers_module

    class _Probe:
        def __init__(self, *args, **kwargs):
            pass

        async def list_models(self):
            return [{"id": "a", "name": "a"}, {"id": "b", "name": "b"}]

    orig = providers_module.LocalProvider
    providers_module.LocalProvider = _Probe  # type: ignore[assignment]
    try:
        model, _, _ = await resolve_slot("http://x/v1", "b")
    finally:
        providers_module.LocalProvider = orig
    assert model == "b"
