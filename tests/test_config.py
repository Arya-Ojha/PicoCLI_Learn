"""Ticket 07 — settings.json loading with sensible defaults."""

import json

from pico_sdk.config import Settings, load_settings


def test_defaults_when_no_file(tmp_path):
    settings = load_settings(tmp_path / "missing.json")
    assert settings.model == "openrouter/free"
    assert settings.reserve_tokens == 16384
    assert settings.session_dir == "~/.pico/sessions"


def test_loads_values_from_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "model": "anthropic/claude-3.5-sonnet",
                "reserve_tokens": 8192,
                "session_dir": "/tmp/sessions",
            }
        ),
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.model == "anthropic/claude-3.5-sonnet"
    assert settings.reserve_tokens == 8192
    assert settings.session_dir == "/tmp/sessions"


def test_missing_keys_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model": "x"}), encoding="utf-8")
    settings = load_settings(path)
    assert settings.model == "x"
    assert settings.reserve_tokens == 16384
    assert settings.context_window == 128_000
