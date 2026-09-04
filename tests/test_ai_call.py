"""Smoke: unified AI call types + text streaming."""

import httpx

from pico_ai.openrouter import OpenRouterProvider
from pico_ai.types import AICallRequest, Message, ToolDefinition


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
