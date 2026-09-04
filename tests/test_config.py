"""Smoke: settings defaults."""

from pico_sdk.config import load_settings


def test_defaults_when_no_file(tmp_path):
    settings = load_settings(tmp_path / "missing.json")
    assert settings.provider == "local"
    assert settings.base_url == "http://localhost:8000/v1"
    assert settings.model == ""  # empty means auto-detect served models
    assert settings.reserve_tokens == 16384
    assert settings.session_dir == "~/.pico/sessions"
