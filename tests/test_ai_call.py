"""Ticket 01 — the unified AI call: types round-trip and OpenRouter normalization."""

import httpx

from pico_ai.openrouter import OpenRouterProvider
from pico_ai.types import AICallRequest, Message, ToolCall, ToolDefinition


def test_types_round_trip_provider_agnostic():
    req = AICallRequest(
        system="you are helpful",
        messages=[Message(role="user", content="hi")],
        tools=[ToolDefinition(name="read", description="read a file", input_schema={"type": "object"})],
        model="anthropic/claude-3.5-sonnet",
    )
    data = req.model_dump()
    assert "openrouter" not in str(data).lower()
    assert AICallRequest.model_validate(data) == req


async def test_openrouter_streams_text():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    async def handler(request):
        return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

    provider = OpenRouterProvider(
        api_key="test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    events = [
        e
        async for e in provider.stream(
            AICallRequest(model="x", messages=[Message(role="user", content="hi")])
        )
    ]
    assert "".join(e.text for e in events if e.kind == "text") == "Hello world"


async def test_openrouter_streams_tool_call():
    sse = (
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"read","arguments":""}}]}}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"path\\":\\"a.txt\\"}"}}]}}]}\n\n'
        'data: {"choices":[{"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    )

    async def handler(request):
        return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

    provider = OpenRouterProvider(
        api_key="test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    events = [
        e
        async for e in provider.stream(
            AICallRequest(
                model="x",
                messages=[Message(role="user", content="read a.txt")],
                tools=[ToolDefinition(name="read", input_schema={"type": "object"})],
            )
        )
    ]
    calls = [e.tool_call for e in events if e.kind == "tool_call"]
    assert len(calls) == 1
    assert calls[0] == ToolCall(id="call_1", name="read", arguments={"path": "a.txt"})
