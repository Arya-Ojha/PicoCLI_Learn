"""OpenRouter provider: streams chat completions and normalizes to StreamEvents."""

from __future__ import annotations

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
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client = client
        # Streaming LLM responses can take a while before the first token; the
        # httpx default (5s) is far too short, so default to a generous read.
        self._timeout = timeout or httpx.Timeout(300.0, connect=10.0)

    async def stream(self, request: AICallRequest) -> AsyncIterator[StreamEvent]:
        payload = self._build_payload(request)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        pending: dict[int, dict] = {}
        try:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    for event in self._parse_chunk(json.loads(data), pending):
                        yield event
        finally:
            if self._client is None:
                await client.aclose()

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
