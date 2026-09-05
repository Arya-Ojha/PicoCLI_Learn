"""Smoke: capability router registry."""

from pico_sdk.router import EXAMPLE_YAML, load_registry, route


def test_route_exact_capability(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(EXAMPLE_YAML, encoding="utf-8")
    registry = load_registry(path)
    assert len(registry) == 3
    model, reason = route("ocr", registry, default="fallback")
    assert model == "nuextract-3-4B-Q4"
    assert "ocr" in reason


def test_route_fallback_skips_testing_only(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(EXAMPLE_YAML, encoding="utf-8")
    registry = load_registry(path)
    model, _ = route("unknown-cap", registry, default="fallback")
    assert model == "qwen2.5-3B-instruct-Q4"


def test_empty_registry_uses_default(tmp_path):
    model, _ = route("code", [], default="fallback-model")
    assert model == "fallback-model"


def test_missing_file_yields_empty(tmp_path):
    assert load_registry(tmp_path / "nope.yaml") == []
