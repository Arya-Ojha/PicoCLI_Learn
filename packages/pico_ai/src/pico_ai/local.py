"""Local provider: streams chat completions from a loopback OpenAI-compatible
server (vLLM, llama.cpp --server, LM Studio) and normalizes to StreamEvents.

No cloud, no API key required: the default endpoint is the local vLLM
server. Everything stays on this machine.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from .types import AICallRequest, StreamEvent, ToolCall, Usage

#: Default endpoint of a local vLLM server (OpenAI-compatible API).
DEFAULT_LOCAL_BASE_URL = "http://localhost:8000/v1"


def normalize_base_url(raw: str) -> str:
    """Normalize a user-typed local endpoint to a ``.../v1`` base URL.

    Accepts a bare host:port (``127.0.0.1:11434``), a full URL with or
    without scheme, and with or without the ``/v1`` suffix. Returns the
    canonical ``http(s)://host:port/v1`` form. Raises ``ValueError`` on
    empty input or an unparseable host.
    """
    from urllib.parse import urlparse

    text = (raw or "").strip().strip("\"'")
    if not text:
        raise ValueError("empty endpoint — enter e.g. http://127.0.0.1:11434")
    if "://" not in text:
        text = f"http://{text}"
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"invalid endpoint: {raw.strip()!r}")
    host = parsed.hostname
    port = f":{parsed.port}" if parsed.port else ""
    path = (parsed.path or "").rstrip("/")
    if path in ("", "/", "/v1"):
        suffix = "/v1"
    else:
        # Keep any custom prefix (e.g. /openai/v1) but ensure /v1 tail.
        suffix = path if path.endswith("/v1") else f"{path}/v1"
    return f"{parsed.scheme}://{host}{port}{suffix}"


class LocalProvider:
    """Streams chat completions from a local OpenAI-compatible server."""

    #: Human-readable name shown in the TUI status bar.
    display_name = "vLLM"

    def __init__(
        self,
        base_url: str = DEFAULT_LOCAL_BASE_URL,
        api_key: str = "",
        client: httpx.AsyncClient | None = None,
        timeout: httpx.Timeout | None = None,
        first_token_timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client
        # Local inference (especially first-token / model load) can take a
        # while; default to a generous read timeout.
        self._timeout = timeout or httpx.Timeout(300.0, connect=10.0)
        # Abort if the local server produces no first token within this many
        # seconds; without it a stalled server looks like an infinite hang.
        self._first_token_timeout = first_token_timeout
        # model id -> whether the model supports tool calling. Local
        # /v1/models responses don't advertise this, so unknown models are
        # assumed to support tools.
        self._tool_support: dict[str, bool] = {}

    async def stream(self, request: AICallRequest) -> AsyncIterator[StreamEvent]:
        payload = self._build_payload(request)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        pending: dict[int, dict] = {}
        response_cm = client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        response: httpx.Response | None = None
        try:
            # Bound the wait for the response headers plus the first SSE line.
            try:
                async with asyncio.timeout(self._first_token_timeout):
                    response = await response_cm.__aenter__()
                    if response.status_code >= 400:
                        body = (await response.aread()).decode(errors="replace")
                        raise RuntimeError(
                            f"local model error {response.status_code} "
                            f"for model '{request.model}': "
                            f"{body[:500]}"
                        )
                    lines = response.aiter_lines()
                    first_line = await anext(lines, None)
            except TimeoutError as exc:
                raise RuntimeError(
                    f"no response from local model within "
                    f"{self._first_token_timeout:g}s "
                    f"(first-token timeout); is the server running at "
                    f"{self._base_url}?"
                ) from exc
            if first_line is not None:
                async for event in self._emit_lines(
                    self._prepend(first_line, lines), pending
                ):
                    yield event
        finally:
            if response is not None:
                await response_cm.__aexit__(None, None, None)
            if self._client is None:
                await client.aclose()

    async def _emit_lines(
        self, lines: AsyncIterator[str], pending: dict[int, dict]
    ) -> AsyncIterator[StreamEvent]:
        """Parse SSE lines and yield normalized stream events."""
        async for line in lines:
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                return
            for event in self._parse_chunk(json.loads(data), pending):
                yield event

    @staticmethod
    async def _prepend(
        first: str, rest: AsyncIterator[str]
    ) -> AsyncIterator[str]:
        yield first
        async for item in rest:
            yield item

    async def list_models(self) -> list[dict]:
        """Return the models served by the local server.

        Each entry is a dict with keys ``id``, ``name``, ``is_free`` (always
        True — local inference costs nothing per call) and
        ``supports_tools`` (assumed True; the OpenAI ``/v1/models`` shape
        does not advertise tool support).
        """
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                f"{self._base_url}/models",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json().get("data", [])
        finally:
            if self._client is None:
                await client.aclose()
        models: list[dict] = []
        for entry in data:
            model_id = entry.get("id", "")
            self._tool_support[model_id] = True
            models.append(
                {
                    "id": model_id,
                    "name": entry.get("id") or model_id,
                    "is_free": True,
                    "supports_tools": True,
                }
            )
        return models

    def _build_payload(self, request: AICallRequest) -> dict:
        messages: list[dict] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        for m in request.messages:
            msg: dict = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in m.tool_calls
                ]
                # An assistant turn that only made tool calls has no text;
                # send null content rather than an empty string.
                if not m.content:
                    msg["content"] = None
            if m.tool_call_id is not None:
                msg["tool_call_id"] = m.tool_call_id
            if m.name is not None:
                msg["name"] = m.name
            messages.append(msg)
        payload: dict = {
            "model": request.model,
            "messages": messages,
            "stream": True,
        }
        # Note: no stream_options.include_usage — vLLM support varies by
        # version and some builds reject unknown fields.
        if request.tools and self._tool_support.get(request.model, True):
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in request.tools
            ]
        return payload

    def _parse_chunk(self, chunk: dict, pending: dict[int, dict]) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                events.append(StreamEvent(kind="text", text=content))
            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
            if reasoning:
                events.append(StreamEvent(kind="thinking", thinking=reasoning))
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                entry = pending.setdefault(idx, {"id": "", "name": "", "args": ""})
                if tc.get("id"):
                    entry["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    entry["name"] = fn["name"]
                if fn.get("arguments"):
                    entry["args"] += fn["arguments"]
            if choice.get("finish_reason") == "tool_calls":
                for idx in sorted(pending):
                    entry = pending[idx]
                    events.append(
                        StreamEvent(
                            kind="tool_call",
                            tool_call=ToolCall(
                                id=entry["id"],
                                name=entry["name"],
                                arguments=self._parse_args(entry["args"]),
                            ),
                        )
                    )
                pending.clear()
        usage = chunk.get("usage")
        if usage:
            events.append(
                StreamEvent(
                    kind="usage",
                    usage=Usage(
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                    ),
                )
            )
        return events

    @staticmethod
    def _parse_args(raw: str) -> dict:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
