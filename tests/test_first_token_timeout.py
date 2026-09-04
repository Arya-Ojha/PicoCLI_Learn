"""Smoke: first-token timeout."""

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
