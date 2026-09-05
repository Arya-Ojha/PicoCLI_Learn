"""Smoke: corpus search, doc read, deliverables, trace panel."""

from pathlib import Path

from pico_core.session import (
    Session,
    UserPayload,
    kb_hit_payload,
    ocr_page_payload,
    router_decision_payload,
)
from pico_sdk.corpus import index_corpus, search
from pico_sdk.deliverables import emit_approval_note, emit_sheet
from pico_sdk.docread import read_document
from pico_tui.trace_panel import format_trace


def test_corpus_search_returns_cited_span(tmp_path: Path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "SOP-1.md").write_text("torque valve to 40 Nm before dispatch", encoding="utf-8")
    chunks = index_corpus(kb)
    assert chunks
    hits = search("valve torque", chunks)
    assert hits and "SOP-1.md" in hits[0].doc


def test_corpus_empty_query_returns_none(tmp_path: Path):
    assert search("", index_corpus(tmp_path)) == []


def test_docread_txt_pages_and_jail(tmp_path: Path):
    (tmp_path / "report.txt").write_text("finding one\n\nfinding two", encoding="utf-8")
    pages = read_document(tmp_path, "report.txt")
    assert isinstance(pages, list) and len(pages) == 2
    assert isinstance(read_document(tmp_path, "../evil.txt"), str)


def test_approval_note_and_sheet_emit(tmp_path: Path):
    doc = emit_approval_note(tmp_path, "note.docx", ["leak at flange"], ["[SOP-1 p1]"])
    assert doc.exists() and doc.suffix == ".docx"
    sheet = emit_sheet(tmp_path, "calc.csv", [["item", "formula", "value"], ["t", "=2*3", "6"]])
    assert sheet.exists()


def test_format_trace_projection():
    session = Session()
    root = session.append(None, UserPayload(content="hi"))
    session.append(root.id, router_decision_payload("ocr", "m", "r"))
    session.append(session.active_leaf_id, kb_hit_payload("d", "c", "p"))
    session.append(session.active_leaf_id, ocr_page_payload(1, "p.png", "t"))
    text = format_trace(session)
    assert "router ocr -> m" in text and "kb d c p" in text and "ocr p1" in text
