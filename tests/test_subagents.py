"""Subagent tools: ocr_read (vision slot) and summarize (summary slot)."""

import httpx
import json
import pytest

from pico_sdk.config import Settings
from pico_sdk.ocr import OcrTool
from pico_sdk.summarize import SummarizeTool


def _vision_settings(**kwargs) -> Settings:
    base = {
        "model": "big",
        "base_url": "http://localhost:8000/v1",
        "vision_model": "vis",
        "vision_base_url": "http://127.0.0.1:11434/v1",
        "summary_model": "small",
        "summary_base_url": "http://127.0.0.1:11434/v1",
    }
    base.update(kwargs)
    return Settings(**base)


def _chat_clientploy(content: str, seen: list) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_ocr_txt_needs_no_endpoint(tmp_path):
    (tmp_path / "r.txt").write_text("alpha\n\nbeta", encoding="utf-8")
    emitted: list = []
    tool = OcrTool(tmp_path, Settings(), on_pages=emitted.append)
    outcome = await tool.run({"path": "r.txt"})
    assert not outcome.is_error
    assert "[p1]" in outcome.content and "[p2]" in outcome.content
    assert len(emitted) == 1 and len(emitted[0]) == 2


async def test_ocr_jail_and_missing(tmp_path):
    tool = OcrTool(tmp_path, Settings())
    assert (await tool.run({"path": "../evil.pdf"})).is_error
    assert (await tool.run({"path": "nope.pdf"})).is_error


async def test_ocr_unconfigured_slot(tmp_path):
    (tmp_path / "a.png").write_bytes(b"\x89PNG fake")
    tool = OcrTool(tmp_path, Settings())
    outcome = await tool.run({"path": "a.png"})
    assert outcome.is_error and "/local" in outcome.content


async def test_ocr_image_calls_vision_endpoint(tmp_path):
    (tmp_path / "scan.png").write_bytes(b"\x89PNG fake-bytes")
    seen: list = []
    tool = OcrTool(
        tmp_path, _vision_settings(), client=_chat_clientploy("hello transcribed", seen)
    )
    outcome = await tool.run({"path": "scan.png"})
    assert not outcome.is_error
    assert "hello transcribed" in outcome.content
    assert str(seen[0].url) == "http://127.0.0.1:11434/v1/chat/completions"
    body = json.loads(seen[0].content.decode())
    assert body["model"] == "vis"
    assert any(
        isinstance(part, dict) and part.get("type") == "image_url"
        for part in body["messages"][0]["content"]
    )


async def test_ocr_pdf_renders_and_transcribes(tmp_path):
    _scan_pdf(tmp_path / "scan.pdf")
    seen: list = []
    emitted: list = []
    tool = OcrTool(
        tmp_path,
        _vision_settings(),
        client=_chat_clientploy("page text here", seen),
        on_pages=emitted.append,
    )
    outcome = await tool.run({"path": "scan.pdf"})
    assert not outcome.is_error
    assert "[p1]" in outcome.content and "page text here" in outcome.content
    assert seen and emitted and len(emitted[0]) == 1
    assert emitted[0][0].png.endswith(".png")


def _scan_pdf(path, pages: int = 1):
    """Write an image-only PDF (no text layer) simulating a true scan."""
    import pymupdf

    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        page.draw_rect(
            pymupdf.Rect(50, 50, 300, 300), color=(0, 0, 0), fill=(0.9, 0.9, 0.9)
        )
    doc.save(path)
    doc.close()


def _mixed_pdf(path):
    """Page 1 digital (text layer), page 2 a scan (no text)."""
    import pymupdf

    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text(
        (72, 72),
        "Digital page one with plenty of embedded text. " * 4,
    )
    p2 = doc.new_page()
    p2.draw_rect(pymupdf.Rect(50, 50, 300, 300), fill=(0.9, 0.9, 0.9))
    doc.save(path)
    doc.close()


async def test_ocr_pdf_text_layer_needs_no_vision_call(tmp_path):
    import pathlib
    import shutil

    root = pathlib.Path(__file__).resolve().parents[1]
    shutil.copy(root / "testpdf.pdf", tmp_path / "testpdf.pdf")
    seen: list = []
    emitted: list = []
    tool = OcrTool(
        tmp_path,
        _vision_settings(),
        client=_chat_clientploy("should never be called", seen),
        on_pages=emitted.append,
    )
    outcome = await tool.run({"path": "testpdf.pdf"})
    assert not outcome.is_error
    assert seen == []  # fast path: zero HTTP calls
    assert "[p1]" in outcome.content
    assert "Welcome to Smallpdf" in outcome.content
    assert len(emitted) == 1 and emitted[0][0].page == 1


async def test_ocr_pdf_text_layer_needs_no_slot(tmp_path):
    import pathlib
    import shutil

    root = pathlib.Path(__file__).resolve().parents[1]
    shutil.copy(root / "testpdf.pdf", tmp_path / "testpdf.pdf")
    tool = OcrTool(tmp_path, Settings())  # no vision model/endpoint
    outcome = await tool.run({"path": "testpdf.pdf"})
    assert not outcome.is_error
    assert "Welcome to Smallpdf" in outcome.content


async def test_ocr_pdf_mixed_text_and_scan(tmp_path):
    _mixed_pdf(tmp_path / "mixed.pdf")
    seen: list = []
    emitted: list = []
    tool = OcrTool(
        tmp_path,
        _vision_settings(),
        client=_chat_clientploy("scan transcription", seen),
        on_pages=emitted.append,
    )
    outcome = await tool.run({"path": "mixed.pdf"})
    assert not outcome.is_error
    assert len(seen) == 1  # only the scanned page hits vision
    assert "[p1]" in outcome.content and "Digital page one" in outcome.content
    assert "[p2]" in outcome.content and "scan transcription" in outcome.content
    assert [e[0].page for e in emitted] == [1, 2]


def _big_png_bytes(width: int = 3000, height: int = 4000) -> bytes:
    from io import BytesIO

    from PIL import Image

    im = Image.new("RGB", (width, height), (200, 210, 220))
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_fit_for_vision_downscales_huge_photo():
    from pico_sdk.ocr import VISION_MAX_SIDE, _fit_for_vision

    from PIL import Image
    from io import BytesIO

    data, mime = _fit_for_vision(_big_png_bytes())
    assert mime == "image/jpeg"
    got = Image.open(BytesIO(data))
    assert max(got.size) <= VISION_MAX_SIDE


def test_fit_for_vision_passthrough_small_line_art(tmp_path):
    import pymupdf

    from pico_sdk.ocr import _fit_for_vision

    doc = pymupdf.open()
    page = doc.new_page(width=400, height=400)
    page.draw_rect(pymupdf.Rect(50, 50, 300, 300), fill=(0.9, 0.9, 0.9))
    raw = doc[0].get_pixmap(dpi=100).tobytes("png")
    doc.close()
    data, mime = _fit_for_vision(raw)
    assert data == raw  # byte-identical: crisp line-art untouched
    assert mime == "image/png"


def test_fit_for_vision_garbage_passes_through():
    from pico_sdk.ocr import _fit_for_vision

    assert _fit_for_vision(b"\x89PNG fake") == (b"\x89PNG fake", "image/png")


def test_ollama_native_url():
    from pico_sdk.ocr import _ollama_native_url

    assert (
        _ollama_native_url("http://127.0.0.1:11434/v1")
        == "http://127.0.0.1:11434/api/chat"
    )
    assert (
        _ollama_native_url("http://127.0.0.1:11434")
        == "http://127.0.0.1:11434/api/chat"
    )
    assert _ollama_native_url("http://localhost:8000/v1") is None
    assert _ollama_native_url("https://openrouter.ai/api/v1") is None


async def test_ocr_image_400_falls_back_to_native(tmp_path):
    (tmp_path / "scan.png").write_bytes(b"\x89PNG fake-bytes")
    calls: list = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(400, json={"error": {"message": "nope"}})
        assert request.url.path.endswith("/api/chat")
        body = json.loads(request.content.decode())
        assert body["messages"][0]["images"] and body["model"] == "vis"
        return httpx.Response(
            200, json={"message": {"content": "native transcription"}}
        )

    settings = _vision_settings()  # vision_base_url is 127.0.0.1:11434/v1
    tool = OcrTool(
        tmp_path, settings,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    outcome = await tool.run({"path": "scan.png"})
    assert not outcome.is_error
    assert "native transcription" in outcome.content
    assert len(calls) == 2


async def test_ocr_image_400_without_ollama_surfaced(tmp_path):
    (tmp_path / "scan.png").write_bytes(b"\x89PNG fake-bytes")
    calls: list = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    settings = _vision_settings(vision_base_url="http://example.com/v1")
    tool = OcrTool(
        tmp_path, settings,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    outcome = await tool.run({"path": "scan.png"})
    assert not outcome.is_error  # per-page failure, not a tool crash
    assert "vision error p1" in outcome.content
    assert len(calls) == 1  # no native retry off-Ollama


async def test_ocr_mode_diagram_selects_diagram_prompt(tmp_path):
    (tmp_path / "pid.png").write_bytes(b"\x89PNG fake-bytes")
    seen: list = []
    tool = OcrTool(
        tmp_path, _vision_settings(), client=_chat_clientploy("tags here", seen)
    )
    outcome = await tool.run({"path": "pid.png", "mode": "diagram"})
    assert not outcome.is_error
    body = json.loads(seen[0].content.decode())
    text_parts = [
        p["text"] for p in body["messages"][0]["content"] if p.get("type") == "text"
    ]
    assert any("engineering drawing" in t for t in text_parts)


async def test_ocr_mode_unknown_is_error(tmp_path):
    (tmp_path / "a.png").write_bytes(b"\x89PNG fake")
    tool = OcrTool(tmp_path, _vision_settings())
    outcome = await tool.run({"path": "a.png", "mode": "translate"})
    assert outcome.is_error and "transcribe" in outcome.content


async def test_ocr_shared_openrouter_slot_sends_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    (tmp_path / "scan.png").write_bytes(b"\x89PNG fake-bytes")
    seen: list = []
    settings = Settings(
        provider="openrouter",
        model="free/model",
        base_url="http://localhost:8000/v1",
    )
    tool = OcrTool(
        tmp_path, settings, client=_chat_clientploy("hi", seen)
    )
    outcome = await tool.run({"path": "scan.png"})
    assert not outcome.is_error
    assert str(seen[0].url) == "https://openrouter.ai/api/v1/chat/completions"
    assert seen[0].headers.get("authorization") == "Bearer test-key"
    assert json.loads(seen[0].content.decode())["model"] == "free/model"


async def test_summarize_shared_openrouter_slot_sends_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    seen: list = []
    settings = Settings(
        provider="openrouter",
        model="free/model",
        base_url="http://localhost:8000/v1",
    )
    tool = SummarizeTool(
        tmp_path, settings, client=_chat_clientploy("the gist", seen)
    )
    outcome = await tool.run({"text": "long document " * 500})
    assert not outcome.is_error and outcome.content == "the gist"
    assert str(seen[0].url) == "https://openrouter.ai/api/v1/chat/completions"
    assert seen[0].headers.get("authorization") == "Bearer test-key"


async def test_ocr_unsupported_suffix(tmp_path):
    (tmp_path / "a.zip").write_bytes(b"PK")
    tool = OcrTool(tmp_path, _vision_settings())
    assert (await tool.run({"path": "a.zip"})).is_error


async def test_ocr_pdf_500_retries_at_lower_dpi(tmp_path):
    _scan_pdf(tmp_path / "scan.pdf")
    calls: list = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "recovered text"}}]}
        )

    tool = OcrTool(
        tmp_path,
        _vision_settings(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    outcome = await tool.run({"path": "scan.pdf"})
    assert not outcome.is_error
    assert "recovered text" in outcome.content
    assert "DPI 100" in outcome.content
    assert len(calls) == 2


async def test_ocr_pdf_empty_transcription_retries_at_lower_dpi(tmp_path):
    _scan_pdf(tmp_path / "scan.pdf")
    calls: list = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "  "}}]}
            )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "recovered text"}}]}
        )

    tool = OcrTool(
        tmp_path,
        _vision_settings(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    outcome = await tool.run({"path": "scan.pdf"})
    assert not outcome.is_error
    assert "recovered text" in outcome.content
    assert len(calls) == 2


async def test_summarize_text_calls_summary_slot(tmp_path):
    seen: list = []
    tool = SummarizeTool(
        tmp_path,
        _vision_settings(),
        client=_chat_clientploy("the gist", seen),
    )
    outcome = await tool.run({"text": "long document " * 500})
    assert not outcome.is_error and outcome.content == "the gist"
    assert str(seen[0].url) == "http://127.0.0.1:11434/v1/chat/completions"
    body = json.loads(seen[0].content.decode())
    assert body["model"] == "small"


async def test_summarize_path_and_pdf_redirect(tmp_path):
    (tmp_path / "doc.md").write_text("hello world", encoding="utf-8")
    seen: list = []
    tool = SummarizeTool(
        tmp_path, _vision_settings(), client=_chat_clientploy("s", seen)
    )
    assert (await tool.run({"path": "doc.md"})).content == "s"
    (tmp_path / "d.pdf").write_bytes(b"%PDF")
    pdf_outcome = await tool.run({"path": "d.pdf"})
    assert pdf_outcome.is_error and "ocr_read" in pdf_outcome.content


async def test_summarize_empty_and_unconfigured(tmp_path):
    tool = SummarizeTool(tmp_path, Settings())
    assert (await tool.run({"text": "   "})).is_error
    assert "not configured" in (await tool.run({"text": "hello"})).content


async def test_subagent_tools_registered_by_default(tmp_path):
    from conftest import FakeProvider, make_session

    session = make_session(FakeProvider([]), tmp_path)
    assert session.tools.get("ocr_read") is not None
    assert session.tools.get("summarize") is not None


async def test_ocr_pages_land_in_trace(tmp_path):
    from pico_core.session import ToolRequestPayload

    from conftest import FakeProvider, make_session

    (tmp_path / "r.txt").write_text("finding one", encoding="utf-8")
    session = make_session(FakeProvider([]), tmp_path)
    ocr = session.tools.get("ocr_read")
    assert ocr is not None
    await ocr.run({"path": "r.txt"})
    subtypes = [
        n.payload.subtype
        for n in session.session.active_branch()
        if isinstance(n.payload, ToolRequestPayload)
    ]
    assert "ocr_page" in subtypes
