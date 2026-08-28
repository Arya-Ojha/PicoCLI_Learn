"""OpenRouter provider: streams chat completions and normalizes to StreamEvents."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from .types import AICallRequest, StreamEvent, ToolCall, Usage


class OpenRouterProvider:
    """Streams chat completions from OpenRouter and normalizes them."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        client: httpx.AsyncClient | None = None,
        timeout: httpx.Timeout | None = None,
        first_token_timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client = client
        # Streaming LLM responses can take a while before the first token; the
        # httpx default (5s) is far too short, so default to a generous read.
        self._timeout = timeout or httpx.Timeout(300.0, connect=10.0)
        # Abort if the model produces no first token within this many seconds;
        # without it a stalled request looks like an infinite hang.
        self._first_token_timeout = first_token_timeout

    async def stream(self, request: AICallRequest) -> AsyncIterator[StreamEvent]:
        payload = self._build_payload(request)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
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
            # Bound the wait for the response headers plus the first SSE line:
            # a stalled upstream (e.g. a broken/free model) would otherwise
            # hang for the full 300s read timeout looking like an infinite
            # spin. Once tokens are flowing, the httpx read timeout governs
            # inter-chunk gaps.
            try:
                async with asyncio.timeout(self._first_token_timeout):
                    response = await response_cm.__aenter__()
                    response.raise_for_status()
                    lines = response.aiter_lines()
                    first_line = await anext(lines, None)
            except TimeoutError as exc:
                raise RuntimeError(
                    f"no response from model within "
                    f"{self._first_token_timeout:g}s "
                    f"(first-token timeout); try another model"
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
        """Return the available models from OpenRouter.

        Each entry is a dict with keys ``id``, ``name`` and ``is_free``.
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
            pricing = entry.get("pricing") or {}
            is_free = (
                str(pricing.get("prompt", "1")).strip() in ("0", "0.0", "-1")
                and str(pricing.get("completion", "1")).strip() in ("0", "0.0", "-1")
            )
            models.append(
                {
                    "id": entry.get("id", ""),
                    "name": entry.get("name") or entry.get("id", ""),
                    "is_free": is_free,
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
            "stream_options": {"include_usage": True},
        }
        if request.tools:
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
