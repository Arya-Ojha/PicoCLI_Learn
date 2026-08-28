"""Tests for model preference persistence across launches."""

import pytest

from pico_sdk import config as sdk_config
from pico_sdk.config import Settings, load_settings, save_settings
from pico_sdk.session import AgentSession
from pico_tui.app import PicoApp, _SessionManager


def test_save_and_load_settings_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(model="vendor/my-model", context_window=99_000)
    save_settings(settings, path)
    loaded = load_settings(path)
    assert loaded.model == "vendor/my-model"
    assert loaded.context_window == 99_000


@pytest.mark.asyncio
async def test_persist_model_writes_to_settings_file(tmp_path, monkeypatch):
    """Picking a model must persist it so the next launch opens with it."""
    settings_path = tmp_path / "settings.json"

    class FakeProvider:
        async def list_models(self):
            return []

        async def stream(self, request):
            yield

    session = AgentSession(
        provider=FakeProvider(),
        model="original/model",
        settings=Settings(session_dir=str(tmp_path)),
        working_dir=tmp_path,
        allow_bash=False,
    )
    monkeypatch.setattr(
        sdk_config, "default_settings_path", lambda: settings_path
    )
    app = PicoApp(_SessionManager(session))
    async with app.run_test():
        app._persist_model("vendor/chosen-model")

    assert settings_path.exists()
    reloaded = load_settings(settings_path)
    assert reloaded.model == "vendor/chosen-model"
