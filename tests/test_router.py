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


async def test_loop_applies_router_per_turn(tmp_path):
    from conftest import FakeProvider
    from pico_core.fsm import AgentLoop
    from pico_core.session import Session
    from pico_core.tools import ToolRegistry

    registry = load_registry_from_text(EXAMPLE_YAML)
    session = Session()
    loop = AgentLoop(
        provider=FakeProvider([]),
        session=session,
        tools=ToolRegistry(),
        model="",
        router_fn=lambda cap: (__import__("pico_sdk.router", fromlist=["route"]).route(cap, registry, default="")[0:2]),
    )
    await loop.run("hi", capability="ocr")
    assert loop.model == "nuextract-3-4B-Q4"
    subtypes = [n.payload.subtype for n in session.active_branch() if n.payload.kind == "tool_request"]
    assert "router_decision" in subtypes


def load_registry_from_text(text: str):
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(text)
        name = f.name
    try:
        return load_registry(Path(name))
    finally:
        Path(name).unlink(missing_ok=True)
