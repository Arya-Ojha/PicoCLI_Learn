"""Summary subagent: ``summarize`` tool backed by the summary slot.

The orchestrator calls this tool for summary-grade work (summarizing a
large document, "give me the gist") so the big model is not spent on
tasks a small fast model handles. Plain non-tools chat call to the
summary endpoint; compaction (/compact) is deliberately untouched and
stays on the orchestrator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pico_core.tools import ToolOutcome, _ensure_within, _resolve

from .corpus import chunk_text

#: Caps: keep one tool call bounded for small local models.
DEFAULT_SUMMARY_TIMEOUT_S = 120.0
MAX_CHUNKS = 20
SUMMARY_CHAR_BUDGET = 4_000

SUMMARY_SYSTEM = (
    "Summarize the following document. Preserve key facts, numbers, names, "
    "decisions, and outstanding items. Reply in the user's language."
)


class SummarizeTool:
    """Summarize text (or a text file) via the summary slot endpoint."""

    name = "summarize"
    description = (
        "Summarize a large document or long text with the fast small model. "
        "Use this when the user asks for a summary, gist, or overview — do "
        "not spend the main model on it. For PDFs, call ocr_read first and "
        "pass the extracted text here. Arguments: "
        '{"text": "<content>"} or {"path": "<cwd-relative .txt/.md file>"}.'
    )
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "path": {"type": "string"},
        },
    }

    def __init__(
        self,
        cwd: Path,
        settings: Any,
        *,
        client: Any | None = None,
        timeout_s: float = DEFAULT_SUMMARY_TIMEOUT_S,
        max_chunks: int = MAX_CHUNKS,
    ) -> None:
        self._cwd = Path(cwd)
        self._settings = settings
        self._client = client
        self._timeout_s = timeout_s
        self._max_chunks = max_chunks

    async def run(self, arguments: dict) -> ToolOutcome:
        text = arguments.get("text", "")
        if arguments.get("path"):
            raw = arguments["path"]
            if _ensure_within(self._cwd, _resolve(self._cwd, raw)) is None:
                return ToolOutcome(
                    content=f"error: path escapes cwd-jail: {raw}", is_error=True
                )
            path = _resolve(self._cwd, raw)
            if not path.exists():
                return ToolOutcome(content=f"error: file not found: {raw}", is_error=True)
            if path.suffix.lower() not in (".txt", ".md"):
                return ToolOutcome(
                    content=(
                        f"error: summarize takes text or .txt/.md; for {path.suffix} "
                        "call ocr_read first, then pass the text here"
                    ),
                    is_error=True,
                )
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                return ToolOutcome(content=f"error: {exc}", is_error=True)
        if not text.strip():
            return ToolOutcome(content="error: nothing to summarize", is_error=True)
        model, base_url = self._settings.slot("summary")
        if not model or not base_url:
            return ToolOutcome(
                content=(
                    "error: summary slot is not configured — set the summary model "
                    "and endpoint with /local"
                ),
                is_error=True,
            )
        chunks = chunk_text(text)[: self._max_chunks]
        truncated = len(chunk_text(text)) > self._max_chunks
        content = "\n\n".join(chunks)
        try:
            summary = await self._summary_call(model, base_url, content)
        except Exception as exc:  # noqa: BLE001 - surface as a result
            hint = (
                " (is the summary endpoint set? use /local)" if not base_url else ""
            )
            return ToolOutcome(content=f"error: summary call failed: {exc}{hint}", is_error=True)
        if len(summary) > SUMMARY_CHAR_BUDGET:
            summary = summary[:SUMMARY_CHAR_BUDGET] + "\n…(truncated)"
        if truncated:
            summary += f"\n(note: input truncated to {self._max_chunks} chunks)"
        return ToolOutcome(content=summary)

    async def _summary_call(self, model: str, base_url: str, content: str) -> str:
        import httpx

        from .providers import auth_headers_for

        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SUMMARY_SYSTEM},
                {"role": "user", "content": content},
            ],
        }
        headers = auth_headers_for(base_url, self._settings)
        timeout = httpx.Timeout(self._timeout_s, connect=10.0)
        if self._client is not None:
            response = await self._client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions", json=payload,
                    headers=headers,
                )
        response.raise_for_status()
        data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected summary response shape: {exc}") from exc
