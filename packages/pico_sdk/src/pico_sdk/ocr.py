"""Vision subagent: ``ocr_read`` tool backed by the vision slot.

The orchestrator (coding/reasoning model) calls this tool when the user
asks about a scanned document, PDF, or image. The tool renders pages to
PNG (DPI 200), sends each to the vision endpoint (OpenAI-compatible
``/chat/completions`` with image content parts), and returns fused text
with ``[pN]`` page refs. Per-page results are also handed to the
``on_pages`` callback so the session can keep ``ocr_page`` trace nodes.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pico_core.tools import ToolOutcome, _ensure_within, _resolve

from .docread import DPI, MAX_PAGES, DocPage, fuse_pages

#: Suffixes sent to the vision endpoint as a single image.
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"})

#: Suffixes rendered page-by-page through a PDF renderer.
PDF_SUFFIXES = frozenset({".pdf"})

#: Spec render resolution (issue 05). Some GPUs crash in the vision
#: projector on large full-page images (HTTP 500 from Ollama); pages that
#: fail are retried once at FALLBACK_DPI.
RENDER_DPI = DPI
FALLBACK_DPI = 100

#: Default caps (see plan): slow CPU vision calls must not stall the loop.
DEFAULT_VISION_TIMEOUT_S = 180.0
DEFAULT_MAX_PAGES = 10
#: Fused tool-result budget; full text lives in the per-page trace nodes.
FUSED_CHAR_BUDGET = 12_000
TRACE_PAGE_CHAR_BUDGET = 8_000

VISION_PROMPT = (
    "Transcribe this page as Markdown, preserving headings, tables, and "
    "reading order. Return only the transcription."
)


class _VisionTooLarge(RuntimeError):
    """The vision server rejected a full-resolution page render (HTTP 500)."""


class _EmptyTranscription(RuntimeError):
    """The vision server returned 200 with no text (context truncated)."""


class OcrTool:
    """Extract text from documents/images via the vision slot endpoint."""

    name = "ocr_read"
    description = (
        "Read a scanned document, PDF, or image and return its text with "
        "page references. Use this whenever the user asks about the contents "
        "of a PDF, scan, or image file. Arguments: "
        '{"path": "<cwd-relative file>", "pages": <max pages, default 10>}.'
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "pages": {"type": "integer"},
        },
        "required": ["path"],
    }

    def __init__(
        self,
        cwd: Path,
        settings: Any,
        *,
        client: Any | None = None,
        timeout_s: float = DEFAULT_VISION_TIMEOUT_S,
        max_pages: int = DEFAULT_MAX_PAGES,
        dpi: int = RENDER_DPI,
        on_pages: Callable[[Sequence[DocPage]], None] | None = None,
    ) -> None:
        self._cwd = Path(cwd)
        self._settings = settings
        self._client = client
        self._timeout_s = timeout_s
        self._max_pages = max_pages
        self._dpi = dpi
        self.on_pages = on_pages

    def _slot(self) -> tuple[str, str]:
        """Return the live ``(model, base_url)`` vision pair."""
        slot = self._settings.slot("vision")
        return slot[0], slot[1]

    async def run(self, arguments: dict) -> ToolOutcome:
        raw = arguments.get("path", "")
        if _ensure_within(self._cwd, _resolve(self._cwd, raw)) is None:
            return ToolOutcome(content=f"error: path escapes cwd-jail: {raw}", is_error=True)
        path = _resolve(self._cwd, raw)
        if not path.exists():
            return ToolOutcome(content=f"error: file not found: {raw}", is_error=True)
        try:
            limit = int(arguments.get("pages", self._max_pages))
        except (TypeError, ValueError):
            limit = self._max_pages
        limit = max(1, min(limit, MAX_PAGES))
        suffix = path.suffix.lower()
        if suffix in (".txt", ".md"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                return ToolOutcome(content=f"error: {exc}", is_error=True)
            pages = [
                DocPage(page=i + 1, png=f"{path.stem}-p{i + 1}-dpi{self._dpi}.png", text=p.strip())
                for i, p in enumerate(
                    [c for c in text.split("\n\n") if c.strip()][:limit]
                )
            ]
            self._emit(pages)
            return ToolOutcome(content=self._fuse(pages, path.name))
        if suffix in IMAGE_SUFFIXES:
            try:
                png_bytes = path.read_bytes()
            except OSError as exc:
                return ToolOutcome(content=f"error: {exc}", is_error=True)
            return await self._transcribe_images(
                [(1, f"{path.stem}-p1-dpi{self._dpi}.png", png_bytes)], path.name
            )
        if suffix in PDF_SUFFIXES:
            try:
                images = _render_pdf_pages(path, limit, self._dpi)
            except ImportError:
                return ToolOutcome(
                    content="error: PDF rendering needs the 'pymupdf' package",
                    is_error=True,
                )
            except Exception as exc:  # noqa: BLE001 - surface as a result
                return ToolOutcome(content=f"error: cannot render PDF: {exc}", is_error=True)
            if not images:
                return ToolOutcome(content=f"error: no pages in {raw}", is_error=True)
            return await self._transcribe_images(images, path.name, pdf_path=path)
        return ToolOutcome(
            content=f"error: unsupported suffix for ocr_read: {suffix or '(none)'}",
            is_error=True,
        )

    async def _transcribe_images(
        self,
        images: list[tuple[int, str, bytes]],
        source: str,
        pdf_path: Path | None = None,
    ) -> ToolOutcome:
        model, base_url = self._slot()
        if not model or not base_url:
            return ToolOutcome(
                content=(
                    "error: vision slot is not configured — set the vision model "
                    "and endpoint with /local"
                ),
                is_error=True,
            )
        pages: list[DocPage] = []
        for page_no, png_name, png_bytes in images:
            try:
                text = await self._vision_page(model, base_url, png_bytes)
            except (_VisionTooLarge, _EmptyTranscription) as exc:
                # Full-res render unusable on this server (GPU projector
                # crash → 500, or 4k context truncation → empty): retry the
                # page once at fallback resolution (evidence: DPI 200 fails,
                # DPI 100 transcribes on the same model/GPU).
                if pdf_path is None or self._dpi <= FALLBACK_DPI:
                    text = f"[vision error p{page_no}: {exc}]"
                else:
                    try:
                        import asyncio as _asyncio

                        # A 500 from Ollama usually means its runner crashed
                        # and needs ~10s to reload the model — wait before
                        # the fallback-resolution retry.
                        await _asyncio.sleep(10)
                        small = _render_pdf_pages(
                            pdf_path, page_no, FALLBACK_DPI, start=page_no - 1
                        )
                        retry_bytes = small[0][2] if small else png_bytes
                        text = await self._vision_page(model, base_url, retry_bytes)
                        text += f"\n(note: page rendered at DPI {FALLBACK_DPI})"
                    except Exception as retry_exc:  # noqa: BLE001 - per-page failure
                        text = f"[vision error p{page_no}: {retry_exc}]"
            except Exception as exc:  # noqa: BLE001 - per-page failure
                text = f"[vision error p{page_no}: {exc}]"
            pages.append(DocPage(page=page_no, png=png_name, text=text))
        self._emit(pages)
        return ToolOutcome(content=self._fuse(pages, source))

    async def _vision_page(self, model: str, base_url: str, png_bytes: bytes) -> str:
        import httpx

        b64 = base64.b64encode(png_bytes).decode("ascii")
        payload = {
            "model": model,
            "stream": False,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
        }
        timeout = httpx.Timeout(self._timeout_s, connect=10.0)
        if self._client is not None:
            response = await self._client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                timeout=timeout,
            )
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions", json=payload
                )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 500:
                raise _VisionTooLarge(
                    f"vision server error 500 for {len(png_bytes)}-byte render"
                ) from exc
            raise
        data = response.json()
        try:
            text = str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected vision response shape: {exc}") from exc
        if not text.strip():
            raise _EmptyTranscription(
                "empty transcription from vision model "
                f"({len(png_bytes)}-byte render)"
            )
        return text

    def _emit(self, pages: Sequence[DocPage]) -> None:
        if self.on_pages is not None and pages:
            self.on_pages(pages)

    @staticmethod
    def _fuse(pages: Sequence[DocPage], source: str) -> str:
        fused = fuse_pages(list(pages))
        if len(fused) > FUSED_CHAR_BUDGET:
            fused = fused[:FUSED_CHAR_BUDGET] + "\n…(truncated; full text in trace)"
        return f"{source} ({len(pages)} page(s)):\n{fused}"


def _render_pdf_pages(
    path: Path, limit: int, dpi: int = RENDER_DPI, start: int = 0
) -> list[tuple[int, str, bytes]]:
    """Render PDF pages to PNG bytes, starting at 0-based ``start``."""
    import pymupdf

    out: list[tuple[int, str, bytes]] = []
    with pymupdf.open(path) as doc:
        for i in range(start, min(len(doc), start + limit)):
            pix = doc[i].get_pixmap(dpi=dpi)
            out.append((i + 1, f"{path.stem}-p{i + 1}-dpi{dpi}.png", pix.tobytes("png")))
    return out


def trace_page_text(text: str) -> str:
    """Cap per-page text stored in ``ocr_page`` trace nodes."""
    if len(text) > TRACE_PAGE_CHAR_BUDGET:
        return text[:TRACE_PAGE_CHAR_BUDGET] + "\n…(truncated)"
    return text
