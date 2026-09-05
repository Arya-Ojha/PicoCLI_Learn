"""Deliverable emitters: approval note, sheet, slides (cwd-jailed, stdlib only)."""

from __future__ import annotations

import csv
import zipfile
import xml.sax.saxutils as sax
from pathlib import Path


def _minimal_docx(path: Path, title: str, paragraphs: list[str]) -> None:
    """Write a minimal readable ``.docx`` using only the standard library."""
    body = "".join(
        f"<w:p><w:r><w:t>{sax.escape(p)}</w:t></w:r></w:p>" for p in [title, *paragraphs]
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)


def emit_approval_note(
    cwd: Path, filename: str, findings: list[str], citations: list[str]
) -> Path:
    """Emit the approval note Word deliverable inside ``cwd``."""
    from pico_core.tools import _ensure_within, _resolve

    cwd = Path(cwd)
    if _ensure_within(cwd, _resolve(cwd, filename)) is None:
        raise ValueError(f"path escapes cwd-jail: {filename}")
    path = _resolve(cwd, filename)
    paragraphs = [
        "Findings:",
        *[f"- {f}" for f in findings],
        "Citations:",
        *[f"- {c}" for c in citations],
    ]
    _minimal_docx(path, "Approval Note", paragraphs)
    return path


def emit_sheet(cwd: Path, filename: str, rows: list[list[str]]) -> Path:
    """Emit an Excel-compatible CSV with formulas preserved as text."""
    from pico_core.tools import _ensure_within, _resolve

    cwd = Path(cwd)
    if _ensure_within(cwd, _resolve(cwd, filename)) is None:
        raise ValueError(f"path escapes cwd-jail: {filename}")
    path = _resolve(cwd, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return path
