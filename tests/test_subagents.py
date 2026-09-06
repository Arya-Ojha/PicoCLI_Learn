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
    import pathlib
    import shutil

    root = pathlib.Path(__file__).resolve().parents[1]
    shutil.copy(root / "testpdf.pdf", tmp_path / "testpdf.pdf")
    seen: list = []
    emitted: list = []
    tool = OcrTool(
        tmp_path,
        _vision_settings(),
        client=_chat_clientploy("page text here", seen),
        on_pages=emitted.append,
    )
    outcome = await tool.run({"path": "testpdf.pdf"})
    assert not outcome.is_error
    assert "[p1]" in outcome.content and "page text here" in outcome.content
    assert seen and emitted and len(emitted[0]) == 1
    assert emitted[0][0].png.endswith(".png")


async def test_ocr_unsupported_suffix(tmp_path):
    (tmp_path / "a.zip").write_bytes(b"PK")
    tool = OcrTool(tmp_path, _vision_settings())
    assert (await tool.run({"path": "a.zip"})).is_error


async def test_ocr_pdf_500_retries_at_lower_dpi(tmp_path):
    import pathlib
    import shutil

    root = pathlib.Path(__file__).resolve().parents[1]
    shutil.copy(root / "testpdf.pdf", tmp_path / "testpdf.pdf")
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
    outcome = await tool.run({"path": "testpdf.pdf"})
    assert not outcome.is_error
    assert "recovered text" in outcome.content
    assert "DPI 100" in outcome.content
    assert len(calls) == 2


async def test_ocr_pdf_empty_transcription_retries_at_lower_dpi(tmp_path):
    import pathlib
    import shutil

    root = pathlib.Path(__file__).resolve().parents[1]
    shutil.copy(root / "testpdf.pdf", tmp_path / "testpdf.pdf")
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
    outcome = await tool.run({"path": "testpdf.pdf"})
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
