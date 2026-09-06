"""Smoke: local (vLLM) provider — streaming, model listing, auto-detect."""

import httpx
import json
import pytest

from pico_ai.local import DEFAULT_LOCAL_BASE_URL, LocalProvider
from pico_ai.types import AICallRequest, Message
from pico_sdk.config import Settings
from pico_sdk.providers import create_provider, resolve_model


async def test_local_streams_text():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    async def handler(request):
        assert str(request.url).startswith("http://localhost:8000/v1/")
        assert "Authorization" not in request.headers  # no key by default
        return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

    provider = LocalProvider(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    events = [
        e
        async for e in provider.stream(
            AICallRequest(model="m", messages=[Message(role="user", content="hi")])
        )
    ]
    assert "".join(e.text for e in events if e.kind == "text") == "Hello world"


async def test_local_list_models_marks_free():
    body = {"object": "list", "data": [{"id": "qwen2.5-coder:32b", "object": "model"}]}

    async def handler(request):
        return httpx.Response(200, json=body)

    provider = LocalProvider(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    models = await provider.list_models()
    assert len(models) == 1
    assert models[0]["id"] == "qwen2.5-coder:32b"
    assert models[0]["is_free"] is True
    assert models[0]["supports_tools"] is True


def test_create_provider_defaults_to_local_without_keys(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    provider = create_provider(Settings())
    assert isinstance(provider, LocalProvider)
    assert provider._base_url == DEFAULT_LOCAL_BASE_URL


class _StubProvider:
    def __init__(self, models=None, fail=False):
        self._models = models
        self._fail = fail

    async def list_models(self):
        if self._fail:
            raise RuntimeError("server down")
        return self._models or []


async def test_resolve_model_auto_detects_single_served():
    provider = _StubProvider([{"id": "m1", "name": "m1"}])
    model, served = await resolve_model(provider, Settings(model=""))
    assert model == "m1"
    assert len(served) == 1


async def test_resolve_model_prefers_configured_when_served():
    provider = _StubProvider([{"id": "m1", "name": "m1"}, {"id": "m2", "name": "m2"}])
    model, served = await resolve_model(provider, Settings(model="m2"))
    assert model == "m2"
    assert len(served) == 2


async def test_resolve_model_falls_back_when_server_down():
    provider = _StubProvider(fail=True)
    model, served = await resolve_model(provider, Settings(model=""))
    assert served == []
    assert model  # some non-empty fallback id


async def test_local_retries_without_tools_when_unsupported():
    sse = 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'
    seen: list = []

    async def handler(request):
        seen.append(request)
        body = json.loads(request.content.decode())
        if "tools" in body:
            return httpx.Response(
                400,
                json={"error": {"message": "m does not support tools"}},
            )
        return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

    from pico_ai.types import ToolDefinition

    provider = LocalProvider(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    request = AICallRequest(
        model="m",
        messages=[Message(role="user", content="hi")],
        tools=[ToolDefinition(name="read", description="r", input_schema={})],
    )
    events = [e async for e in provider.stream(request)]
    assert "".join(e.text for e in events if e.kind == "text") == "hi"
    assert len(seen) == 2
    assert "tools" in json.loads(seen[0].content.decode())
    assert "tools" not in json.loads(seen[1].content.decode())
    # The model is remembered as no-tools: the next call omits tools outright.
    seen.clear()
    events = [e async for e in provider.stream(request)]
    assert "".join(e.text for e in events if e.kind == "text") == "hi"
    assert len(seen) == 1
    assert "tools" not in json.loads(seen[0].content.decode())


async def test_local_still_raises_on_other_400s():
    async def handler(request):
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    provider = LocalProvider(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(RuntimeError, match="local model error 400"):
        async for _ in provider.stream(
            AICallRequest(model="m", messages=[Message(role="user", content="hi")])
        ):
            pass
