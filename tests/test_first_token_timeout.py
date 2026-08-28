"""Tests for the first-token timeout on the streaming provider."""

import httpx
import pytest

from pico_ai.openrouter import OpenRouterProvider
from pico_ai.types import AICallRequest, Message


def _request() -> AICallRequest:
    return AICallRequest(
        model="test/model",
        messages=[Message(role="user", content="hi")],
    )


@pytest.mark.asyncio
async def test_stream_times_out_when_no_first_line():
    """A stalled upstream must raise quickly, not hang for the read timeout."""

    class StallTransport(httpx.AsyncHTTPTransport):
        async def handle_async_request(self, request):  # noqa: ANN001, ANN202
            import asyncio

            # Simulate a server that accepts the request but never sends a
            # response body: the read would block well past the first-token
            # timeout.
            await asyncio.sleep(10)
            return httpx.Response(
                200, content=b"", headers={"content-type": "text/event-stream"}
            )

    provider = OpenRouterProvider(
        api_key="test",
        client=httpx.AsyncClient(transport=StallTransport()),
        first_token_timeout=0.2,
    )
    with pytest.raises(RuntimeError, match="first-token timeout"):
        async for _ in provider.stream(_request()):
            pass


@pytest.mark.asyncio
async def test_stream_yields_events_after_first_line():
    """Normal streams are unaffected by the first-token timeout."""
    sse = (
        'data: {"choices": [{"delta": {"content": "hello"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=sse, headers={"content-type": "text/event-stream"}
        )

    provider = OpenRouterProvider(
        api_key="test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        first_token_timeout=5.0,
    )
    events = [event async for event in provider.stream(_request())]
    assert any(e.kind == "text" and e.text == "hello" for e in events)
