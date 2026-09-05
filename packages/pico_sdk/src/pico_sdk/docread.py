"""Document read: cwd-jailed page pipeline (NuExtract-compatible stub)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DPI = 200
LOCAL_VLM_ID = "nuextract-3-4B-Q4"
VISION_ALIAS = "openrouter-vision-alias"
MAX_PAGES = 20


@dataclass
class DocPage:
    page: int
    png: str
    text: str


def fuse_pages(pages: list[DocPage], per_page: int = 200) -> str:
    """Rolling fuse: join the head of each page for long PDFs."""
    return "\n".join(f"[p{p.page}] {p.text[:per_page]}" for p in pages)


def read_document(cwd: Path, raw_path: str) -> list[DocPage] | str:
    """Read a document inside ``cwd`` into pages.

    Returns a list of pages or an error string when the path escapes the jail.
    ``.txt``/``.md`` are split into page-sized pieces; other suffixes return a
    placeholder recording that the local VLM (``LOCAL_VLM_ID`` at ``DPI`` DPI,
    ``VISION_ALIAS`` for routing tests) would handle them.
    """
    from pico_core.tools import _ensure_within, _resolve

    cwd = Path(cwd)
    if _ensure_within(cwd, _resolve(cwd, raw_path)) is None:
        return f"error: path escapes cwd-jail: {raw_path}"
    path = _resolve(cwd, raw_path)
    if not path.exists():
        return f"error: file not found: {raw_path}"
    if path.suffix.lower() in (".txt", ".md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return f"error: {exc}"
        pages = [p for p in text.split("\n\n") if p.strip()]
        return [
            DocPage(page=i + 1, png=f"{path.stem}-p{i + 1}-dpi{DPI}.png", text=p.strip())
            for i, p in enumerate(pages[:MAX_PAGES])
        ]
    return (
        f"queued for local VLM: {path.name} ({LOCAL_VLM_ID}, DPI {DPI}; "
        f"alias {VISION_ALIAS} for routing tests)"
    )
