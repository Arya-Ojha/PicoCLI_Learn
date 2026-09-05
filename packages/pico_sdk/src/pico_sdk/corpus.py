"""Local corpus: folder mount, chunk, keyword search with hard citations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    doc: str
    chunk_id: str
    page: str
    text: str


def chunk_text(text: str, size: int = 2000, overlap: int = 400) -> list[str]:
    """Split ``text`` into overlapping chunks (approx 512/100 tokens)."""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        if start + size >= len(text):
            break
        start += size - overlap
    return chunks


def index_corpus(root: Path) -> list[Chunk]:
    """Index ``*.md``/``*.txt`` under ``root``; skips hidden dirs."""
    root = Path(root)
    out: list[Chunk] = []
    if not root.is_dir():
        return out
    for file in sorted(root.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in (".md", ".txt"):
            continue
        if any(part.startswith(".") for part in file.relative_to(root).parts):
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, piece in enumerate(chunk_text(text)):
            out.append(Chunk(doc=file.name, chunk_id=f"c{i}", page=f"p{i + 1}", text=piece))
    return out


def search(query: str, chunks: list[Chunk], top_k: int = 5) -> list[Chunk]:
    """Rank chunks by token overlap with ``query`` (CPU, offline)."""
    terms = {t.lower() for t in query.split() if t.strip()}
    if not terms:
        return []
    scored: list[tuple[int, Chunk]] = []
    for ch in chunks:
        hay = ch.text.lower()
        score = sum(1 for t in terms if t in hay)
        if score:
            scored.append((score, ch))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [c for _, c in scored[:top_k]]
