"""Smoke: settings defaults."""

from pico_sdk.config import load_settings


def test_defaults_when_no_file(tmp_path):
    settings = load_settings(tmp_path / "missing.json")
    assert settings.model == "openrouter/free"
    assert settings.reserve_tokens == 16384
    assert settings.session_dir == "~/.pico/sessions"
