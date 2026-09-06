"""Vision subagent: ``ocr_read`` tool backed by the vision slot.

The orchestrator (coding/reasoning model) calls this tool when the user
asks about a scanned document, PDF, or image. PDF pages with an embedded
text layer return it directly (fast path, no model call); pages without
one are rendered to PNG (DPI 200) and sent to the vision endpoint
(OpenAI-compatible ``/chat/completions`` with image content parts), and
text plus image inputs return fused text with ``[pN]`` page refs. Per-page
results are handed to the ``on_pages`` callback incrementally as each page
completes, so the session keeps ``ocr_page`` trace nodes even during slow
vision runs.
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

#: Minimum non-whitespace characters for a PDF page's embedded text layer
#: to count as digital (returned directly, no vision call); sparser pages
#: are treated as scans and sent to the vision endpoint.
TEXT_LAYER_MIN_CHARS = 50

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

#: Prompt for free-form photos and pictures (handwriting photos, site
#: photos, whiteboards): describe rather than transcribe.
DESCRIBE_PROMPT = (
    "Describe this image in detail in Markdown: the scene and setting, the "
    "objects and their layout, and any visible text transcribed exactly. "
    "If the image is a photo of handwriting, transcribe the handwriting "
    "exactly as written, preserving line breaks where possible."
)

#: Prompt for engineering drawings (P&ID, schematics, plans, wiring
#: diagrams): structured extraction, not free transcription.
DIAGRAM_PROMPT = (
    "You are reading an engineering drawing (e.g. P&ID, schematic, plan, "
    "wiring diagram). Describe it structurally in Markdown with these "
    "sections: 1) Drawing type and the main equipment shown. "
    "2) Instrument and component tags with their IDs, transcribed exactly. "
    "3) Streams and flows with their labels and directions. "
    "4) Control loops as sensor-controller-actuator chains. "
    "5) Title block, legend, and notes if visible. "
    "If a tag or label is illegible or absent, say so — do not guess IDs."
)

#: Valid ``mode`` arguments for ``ocr_read`` (see ``OcrTool.input_schema``).
MODES = ("transcribe", "describe", "diagram")

#: Longest image side sent to the vision endpoint. Full-camera photos
#: (e.g. 3879px) stall or break small local servers, so larger inputs are
#: downscaled (quality-first 2048px keeps small instrument tags legible).
VISION_MAX_SIDE = 2048

#: Above this many bytes the upload is JPEG-recompressed even when the
#: dimensions fit (uncompressed PNG photos can still be multi-MB).
VISION_MAX_BYTES = 2_000_000


class _VisionTooLarge(RuntimeError):
    """The vision server rejected a full-resolution page render (HTTP 500)."""


class _EmptyTranscription(RuntimeError):
    """The vision server returned 200 with no text (context truncated)."""


class OcrTool:
    """Extract text from documents/images via the vision slot endpoint."""

    name = "ocr_read"
    description = (
        "Read a scanned document, PDF, or image and return its text with "
        "page references. PDF pages with an embedded text layer are returned "
        "directly (fast, no model call); scanned pages and images are "
        "transcribed via the vision endpoint. Use this whenever the user asks "
        "about the contents of a PDF, scan, or image file. Arguments: "
        '{"path": "<cwd-relative file>", "pages": <max pages, default 10>, '
        '"mode": "transcribe" (default, exact transcription) | "describe" '
        "(scene/object description, photos) | \"diagram\" (structured "
        "engineering-drawing readout: equipment, tags, streams, loops)}."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "pages": {"type": "integer"},
            "mode": {"type": "string", "enum": list(MODES)},
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
        mode = str(arguments.get("mode") or "transcribe").strip().lower()
        if mode not in MODES:
            return ToolOutcome(
                content=f"error: unknown mode {arguments.get('mode')!r} — use one of: {', '.join(MODES)}",
                is_error=True,
            )
        prompt = {"transcribe": VISION_PROMPT, "describe": DESCRIBE_PROMPT, "diagram": DIAGRAM_PROMPT}[mode]
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
                [(1, f"{path.stem}-p1-dpi{self._dpi}.png", png_bytes)], path.name,
                prompt=prompt,
            )
        if suffix in PDF_SUFFIXES:
            try:
                layers = _pdf_text_layers(path, limit)
            except ImportError:
                return ToolOutcome(
                    content="error: PDF rendering needs the 'pymupdf' package",
                    is_error=True,
                )
            except Exception as exc:  # noqa: BLE001 - surface as a result
                return ToolOutcome(content=f"error: cannot render PDF: {exc}", is_error=True)
            if not layers:
                return ToolOutcome(content=f"error: no pages in {raw}", is_error=True)
            # Only scanned pages need the vision endpoint; digital pages
            # return their embedded text immediately (no model call, no wait).
            model, base_url = "", ""
            if any(not _has_text_layer(t) for t in layers):
                model, base_url = self._slot()
                if not model or not base_url:
                    return ToolOutcome(
                        content=(
                            "error: vision slot is not configured — set the vision model "
                            "and endpoint with /local"
                        ),
                        is_error=True,
                    )
            doc_pages: list[DocPage] = []
            for i, layer in enumerate(layers):
                page_no = i + 1
                png_name = f"{path.stem}-p{page_no}-dpi{self._dpi}.png"
                if _has_text_layer(layer):
                    page = DocPage(page=page_no, png=png_name, text=layer.strip())
                    doc_pages.append(page)
                    self._emit([page])
                    continue
                try:
                    rendered = _render_pdf_pages(path, 1, self._dpi, start=i)
                except Exception as exc:  # noqa: BLE001 - per-page failure
                    text = f"[vision error p{page_no}: cannot render PDF: {exc}]"
                    page = DocPage(page=page_no, png=png_name, text=text)
                    doc_pages.append(page)
                    self._emit([page])
                    continue
                if not rendered:
                    text = f"[vision error p{page_no}: no render output]"
                    page = DocPage(page=page_no, png=png_name, text=text)
                    doc_pages.append(page)
                    self._emit([page])
                    continue
                text = await self._transcribe_page(
                    model, base_url, page_no, rendered[0][2],
                    prompt=prompt, pdf_path=path,
                )
                page = DocPage(page=page_no, png=png_name, text=text)
                doc_pages.append(page)
                self._emit([page])
            return ToolOutcome(content=self._fuse(doc_pages, path.name))
        return ToolOutcome(
            content=f"error: unsupported suffix for ocr_read: {suffix or '(none)'}",
            is_error=True,
        )

    async def _transcribe_images(
        self,
        images: list[tuple[int, str, bytes]],
        source: str,
        prompt: str,
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
            text = await self._transcribe_page(
                model, base_url, page_no, png_bytes,
                prompt=prompt, pdf_path=pdf_path,
            )
            page = DocPage(page=page_no, png=png_name, text=text)
            pages.append(page)
            self._emit([page])
        return ToolOutcome(content=self._fuse(pages, source))

    async def _transcribe_page(
        self,
        model: str,
        base_url: str,
        page_no: int,
        png_bytes: bytes,
        prompt: str,
        *,
        pdf_path: Path | None = None,
    ) -> str:
        """Transcribe one rendered page, with a lower-DPI retry on failure."""
        try:
            return await self._vision_page(model, base_url, png_bytes, prompt)
        except (_VisionTooLarge, _EmptyTranscription) as exc:
            # Full-res render unusable on this server (GPU projector
            # crash → 500, or 4k context truncation → empty): retry the
            # page once at fallback resolution (evidence: DPI 200 fails,
            # DPI 100 transcribes on the same model/GPU).
            if pdf_path is None or self._dpi <= FALLBACK_DPI:
                return f"[vision error p{page_no}: {exc}]"
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
                text = await self._vision_page(model, base_url, retry_bytes, prompt)
                return text + f"\n(note: page rendered at DPI {FALLBACK_DPI})"
            except Exception as retry_exc:  # noqa: BLE001 - per-page failure
                return f"[vision error p{page_no}: {retry_exc}]"
        except Exception as exc:  # noqa: BLE001 - per-page failure
            return f"[vision error p{page_no}: {exc}]"

    async def _vision_page(
        self, model: str, base_url: str, png_bytes: bytes, prompt: str
    ) -> str:
        import httpx

        from .providers import auth_headers_for

        fitted, mime = _fit_for_vision(png_bytes)
        b64 = base64.b64encode(fitted).decode("ascii")
        headers = auth_headers_for(base_url, self._settings)
        payload = {
            "model": model,
            "stream": False,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
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
                headers=headers,
                timeout=timeout,
            )
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions", json=payload,
                    headers=headers,
                )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 500:
                raise _VisionTooLarge(
                    f"vision server error 500 for {len(png_bytes)}-byte render"
                ) from exc
            if exc.response is not None and exc.response.status_code == 400:
                # Some Ollama builds reject images on the OpenAI-compatible
                # endpoint while the native /api/chat accepts them.
                native = _ollama_native_url(base_url)
                if native is not None:
                    return await self._vision_page_native(
                        native, model, prompt, b64
                    )
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

    async def _vision_page_native(
        self, url: str, model: str, prompt: str, b64: str
    ) -> str:
        """One-shot transcription via Ollama's native ``/api/chat`` shape."""
        import httpx

        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "user", "content": prompt, "images": [b64]},
            ],
            "options": {"temperature": 0.0},
        }
        timeout = httpx.Timeout(self._timeout_s, connect=10.0)
        if self._client is not None:
            response = await self._client.post(url, json=payload, timeout=timeout)
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = ""
            if exc.response is not None:
                try:
                    body = exc.response.text[:300]
                except Exception:
                    body = ""
            raise RuntimeError(
                f"vision native endpoint error {exc.response.status_code if exc.response is not None else '?'}: {body}"
            ) from exc
        try:
            text = str(response.json()["message"]["content"] or "")
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                f"unexpected native vision response shape: {exc}"
            ) from exc
        if not text.strip():
            raise _EmptyTranscription("empty transcription from native vision call")
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


def _pdf_text_layers(path: Path, limit: int) -> list[str]:
    """Return the embedded text of up to ``limit`` PDF pages.

    Empty strings mark pages with no text layer (true scans). Raises
    ``ImportError`` when ``pymupdf`` is missing so the caller can report it.
    """
    import pymupdf

    out: list[str] = []
    with pymupdf.open(path) as doc:
        for i in range(min(len(doc), limit)):
            out.append(doc[i].get_text())
    return out


def _has_text_layer(text: str) -> bool:
    """True when the embedded text is substantial enough to use directly."""
    return sum(1 for ch in text if not ch.isspace()) >= TEXT_LAYER_MIN_CHARS


def _fit_for_vision(raw: bytes) -> tuple[bytes, str]:
    """Shrink an image upload to what small vision servers handle.

    Returns ``(data, mime)``. Inputs within ``VISION_MAX_SIDE`` and
    ``VISION_MAX_BYTES`` pass through byte-identical (line-art stays crisp);
    larger ones are downscaled and JPEG-recompressed. Anything undecodable
    (or Pillow missing) passes through as ``image/png`` — the endpoint, not
    us, decides.
    """
    try:
        from io import BytesIO

        from PIL import Image
    except ImportError:
        return raw, "image/png"
    try:
        im = Image.open(BytesIO(raw))
        fmt = (im.format or "PNG").lower()
        rgb = im.convert("RGB")
    except Exception:
        return raw, "image/png"
    if max(rgb.size) <= VISION_MAX_SIDE and len(raw) <= VISION_MAX_BYTES:
        mime = {"jpeg": "image/jpeg", "jpg": "image/jpeg"}.get(fmt, f"image/{fmt}")
        return raw, mime
    resampling = getattr(Image, "Resampling", Image)
    if max(rgb.size) > VISION_MAX_SIDE:
        rgb.thumbnail(
            (VISION_MAX_SIDE, VISION_MAX_SIDE), resampling.LANCZOS  # type: ignore[attr-defined]
        )
    buf = BytesIO()
    rgb.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def _ollama_native_url(base_url: str) -> str | None:
    """Return the native ``/api/chat`` URL for Ollama endpoints, else None."""
    low = base_url.lower()
    if "11434" not in low and "ollama" not in low:
        return None
    root = base_url.rstrip("/")
    if root.lower().endswith("/v1"):
        root = root[: -len("/v1")]
    return root.rstrip("/") + "/api/chat"


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
