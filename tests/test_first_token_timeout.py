"""Tests for the first-token timeout on the streaming provider."""

import httpx
import pytest

from pico_ai.openrouter import OpenRouterProvider
from pico_ai.types import AICallRequest, Message, ToolDefinition
from pico_tui.model_picker import ModelPickerScreen


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
async def test_full_flow_pick_model_then_prompt_sends_request(tmp_path, monkeypatch):
    """End-to-end: /model picker selection switches model and the next prompt
    actually reaches the provider with the new model id."""
    from pico_ai.types import StreamEvent
    from pico_sdk.config import Settings
    from pico_sdk.session import AgentSession
    from pico_tui.app import PicoApp, _SessionManager

    class RecordingProvider:
        def __init__(self):
            self.calls = []

        async def list_models(self):
            return [
                {"id": "b/free", "name": "Beta Free", "is_free": True},
                {"id": "a/paid", "name": "Alpha Paid", "is_free": False},
            ]

        async def stream(self, request):
            self.calls.append(request)
            yield StreamEvent(kind="text", text="ok")

    provider = RecordingProvider()
    session = AgentSession(
        provider=provider,
        model="original/model",
        settings=Settings(session_dir=str(tmp_path)),
        working_dir=tmp_path,
        allow_bash=False,
    )
    app = PicoApp(_SessionManager(session))
    async with app.run_test() as pilot:
        # 1. open the picker via /model
        app.query_one("#input-bar").value = "/model"
        await pilot.press("enter")
        await pilot.pause()

        from textual.widgets import OptionList

        await pilot.pause()
        option_list = app.screen.query_one("#model-picker-list", OptionList)
        option_list.highlighted = 0  # sorted: free first -> b/free
        option_list.action_select()
        await pilot.pause()
        assert session.model == "b/free"

        # 2. send a prompt; the provider must receive a request with the model
        app.query_one("#input-bar").value = "hi"
        await pilot.press("enter")
        await pilot.pause()

    assert provider.calls, "no request reached the provider!"
    assert provider.calls[0].model == "b/free"


@pytest.mark.asyncio
async def test_stream_surfaces_api_error_body():
    """A 400 response must surface the API's error body, not just the status."""
    error_json = b'{"error": {"message": "Tool use is not supported"}}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=error_json)

    provider = OpenRouterProvider(
        api_key="test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(RuntimeError, match="Tool use is not supported"):
        async for _ in provider.stream(_request()):
            pass


@pytest.mark.asyncio
async def test_tools_omitted_for_models_without_tool_support():
    """Models that reject tools get a payload without tools instead of a 400."""
    provider = OpenRouterProvider(api_key="test")
    provider._tool_support["free/no-tools"] = False

    request = AICallRequest(
        model="free/no-tools",
        messages=[Message(role="user", content="hi")],
        tools=[ToolDefinition(
            name="read", description="read", input_schema={"type": "object"}
        )],
    )
    payload = provider._build_payload(request)
    assert "tools" not in payload

    provider._tool_support["paid/tools"] = True
    request2 = AICallRequest(
        model="paid/tools",
        messages=[Message(role="user", content="hi")],
        tools=request.tools,
    )
    payload2 = provider._build_payload(request2)
    assert "tools" in payload2


@pytest.mark.asyncio
async def test_list_models_records_tool_support():
    """list_models populates the tool-support cache used by _build_payload."""

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "data": [
                    {
                        "id": "m/no-tools",
                        "name": "No Tools",
                        "pricing": {"prompt": "0", "completion": "0"},
                        "supported_parameters": ["temperature"],
                    },
                    {
                        "id": "m/tools",
                        "name": "With Tools",
                        "pricing": {"prompt": "0", "completion": "0"},
                        "supported_parameters": ["tools", "tool_choice"],
                    },
                ]
            }

    class FakeClient:
        async def get(self, *args, **kwargs) -> FakeResponse:
            return FakeResponse()

        async def aclose(self) -> None:
            pass

    provider = OpenRouterProvider(api_key="test", client=FakeClient())
    models = await provider.list_models()
    by_id = {m["id"]: m for m in models}
    assert by_id["m/no-tools"]["supports_tools"] is False
    assert by_id["m/tools"]["supports_tools"] is True
    assert provider._tool_support["m/no-tools"] is False


@pytest.mark.asyncio
async def test_picker_returns_selected_model_id():
    """Regression: selecting an option must dismiss with the model's id.

    The selected event's index attribute name differs across Textual
    versions, which previously crashed silently and no model was set.
    """
    from typing import Optional

    from textual.app import App
    from textual.widgets import Label, OptionList

    models = [
        {"id": "a/paid", "name": "Alpha Paid", "is_free": False},
        {"id": "b/free", "name": "Beta Free", "is_free": True},
    ]

    class Host(App[Optional[str]]):
        def compose(self):
            yield Label("host")

    app = Host()
    async with app.run_test() as pilot:
        captured: list[str | None] = []
        screen = ModelPickerScreen(models)
        app.push_screen(screen, callback=captured.append)
        await pilot.pause()

        option_list = screen.query_one("#model-picker-list", OptionList)
        option_list.highlighted = 0
        option_list.action_select()  # simulates Enter / click selection
        await pilot.pause()

    assert captured == ["b/free"]


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
