"""Smoke: settings persistence round-trip."""

from pico_sdk.config import Settings, load_settings, save_settings


def test_save_and_load_settings_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(model="vendor/my-model", context_window=99_000)
    save_settings(settings, path)
    loaded = load_settings(path)
    assert loaded.model == "vendor/my-model"
    assert loaded.context_window == 99_000
