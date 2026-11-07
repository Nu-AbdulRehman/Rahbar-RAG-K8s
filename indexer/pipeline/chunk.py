"""Stage 3: Chunk. Structure-aware, with overlap.

The unit is the word (whitespace-separated token): CHUNK_SIZE=400 means at most 400
words per chunk, including the heading line every chunk starts with.

Order of splitting: sections (the "# " headings extract marked), then paragraphs, then
sentences (or table rows), then words for a sentence that is longer than a chunk on its
own. Chunks never cross a section boundary, and every chunk starts with its section
heading, so a heading is never separated from its first paragraph.
"""

from __future__ import annotations

import re

from .models import Chunk, Document

FRONT_MATTER = "(front matter)"      # the section of any text before the first heading
# A new paragraph starts at a clause number, a list marker or a table row.
PARAGRAPH_START = re.compile(
    r"^(\d{1,2}(\.\d{1,2})+\.?\s|\d{1,2}[.)]\s|[a-z][.)]\s|\([a-z0-9ivx]+\)\s|[-•*▪]\s|\|)")
SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")


def _paragraphs(doc: Document) -> list[tuple[str, list[tuple[str, int]]]]:
    """[(section heading, [(paragraph text, page), ...]), ...] in document order."""
    sections: list[tuple[str, list[tuple[str, int]]]] = [(FRONT_MATTER, [])]
    lines: list[str] = []
    start_page = 0

    def flush() -> None:
        if lines:
            joiner = "\n" if lines[0].startswith("|") else " "
            sections[-1][1].append((joiner.join(lines), start_page))
            lines.clear()

    for page in doc.pages:
        for raw in page.text.split("\n"):
            line = raw.strip()
            if line.startswith("# "):
                flush()
                sections.append((line[2:].strip(), []))
                continue
            table, prev_table = line.startswith("|"), bool(lines) and lines[-1].startswith("|")
            ends_sentence = bool(lines) and lines[-1].endswith((".", ":", ";", "?", "!"))
            if not line or (lines and (table != prev_table
                                       or (not table and (PARAGRAPH_START.match(line)
                                                          or ends_sentence)))):
                flush()
            if line:
                if not lines:
                    start_page = page.page
                lines.append(line)
        flush()                       # a paragraph that ends a page starts again on the next
    return [(h, paras) for h, paras in sections if paras]


def _units(text: str, size: int) -> list[str]:
    """Split a paragraph that does not fit into one chunk: table rows, or sentences, then
    fixed word windows for any single sentence longer than a chunk."""
    if len(text.split()) <= size:
        return [text]
    parts = text.split("\n") if text.startswith("|") else SENTENCE_END.split(text)
    out: list[str] = []
    for part in parts:
        words = part.split()
        out.extend(" ".join(words[i:i + size]) for i in range(0, len(words), size))
    return out


def chunk(doc: Document, size: int, overlap: int) -> list[Chunk]:
    """Split on sections, then paragraphs, then sentences, keeping each chunk under
    `size` words, with `overlap` words shared between neighbours in one section. Every
    chunk keeps the section heading it sits under, its page, doc_version and superseded."""
    if not 0 <= overlap < size:
        raise ValueError(f"CHUNK_OVERLAP ({overlap}) must be at least 0 and below "
                         f"CHUNK_SIZE ({size})")
    chunks: list[Chunk] = []

    def emit(section: str, body: list[str], page: int) -> None:
        chunks.append(Chunk(id=f"{doc.source}#{len(chunks):04d}",
                            text=section + "\n" + "\n".join(body), source=doc.source,
                            section=section, page=page, doc_version=doc.doc_version,
                            superseded=doc.superseded))

    for section, paragraphs in _paragraphs(doc):
        budget = max(1, size - len(section.split()))
        body: list[str] = []
        page = paragraphs[0][1]
        fresh = 0                     # words in body that are new, not overlap
        for text, para_page in paragraphs:
            for unit in _units(text, budget):
                n = len(unit.split())
                if body and sum(len(b.split()) for b in body) + n > budget:
                    emit(section, body, page)
                    tail = " ".join(" ".join(body).split()[-overlap:]) if overlap else ""
                    body, fresh = ([tail] if tail and len(tail.split()) + n <= budget
                                   else []), 0
                if not fresh:
                    page = para_page
                body.append(unit)
                fresh += n
        if fresh:
            emit(section, body, page)
    return chunks
