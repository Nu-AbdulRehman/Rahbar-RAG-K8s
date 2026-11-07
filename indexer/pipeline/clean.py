"""Stage 2: Clean. Remove artefacts without destroying structure.

Rules (docs/PIPELINE.md, "Cleaning"):
1. Drop running headers and footers: a line, ignoring digits, that repeats on at least
   REPEAT_SHARE of a document's pages ("Student Handbook 2026 12", "NATIONAL UNIVERSITY
   OF COMPUTER AND EMERGING SCIENCES"). Only for documents of MIN_PAGES pages or more.
2. Drop lines that are only a page number ("17", "IV").
3. Drop table-of-contents entries: dot leaders anywhere, and lines ending in a page
   number on a page that has a "Contents" title.
4. Drop the byte-order mark and collapse runs of blank lines.

Deliberately kept: clause numbers at the start of a line ("1.21 Students are ..."). They
look like noise but they are exact terms a student asks about.
"""

from __future__ import annotations

import re
from collections import Counter

from .models import Document, Page

BOM = chr(0xFEFF)
REPEAT_SHARE = 0.4
MIN_PAGES = 4
PAGE_NUMBER = re.compile(r"^(#\s+)?(\d{1,3}|\d( \d){1,2}|[IVXLC]{1,6}|[ivxlc]{1,6})$")
DOT_LEADER = re.compile(r"(\.\s?){4,}|…{2,}")
TOC_TITLE = re.compile(r"^(#\s+)?(table of )?contents$", re.I)
TOC_ENTRY = re.compile(r"\s(\d{1,3}|[IVX]{1,5})$")


def _key(line: str) -> str:
    """What a running header looks like with its page number and spacing ignored:
    "U ndergraduate Academic Rules and Regulations 2026 11" is the same footer."""
    return re.sub(r"[^a-z]", "", line.removeprefix("# ").lower())


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat on every page; keep headings and
    section boundaries, because chunking and citations depend on them."""
    pages = [p.text.replace(BOM, "").split("\n") for p in doc.pages]
    repeated: set[str] = set()
    if len(pages) >= MIN_PAGES:
        # A key needs letters: "6.2" on its own line (an OCR'd clause number) repeats
        # on many pages too, and must survive as an exact term.
        seen = Counter(k for lines in pages for k in {_key(line) for line in lines}
                       if len(k) >= 3)
        repeated = {k for k, n in seen.items() if n >= max(3, REPEAT_SHARE * len(pages))}

    cleaned = []
    for page, lines in zip(doc.pages, pages):
        toc = any(TOC_TITLE.match(line.strip()) for line in lines)
        kept = []
        for raw in lines:
            line = raw.strip()
            if not line:
                kept.append("")
                continue
            if _key(line) in repeated or PAGE_NUMBER.match(line) or DOT_LEADER.search(line):
                continue
            if toc and (TOC_TITLE.match(line) or TOC_ENTRY.search(line)):
                continue
            kept.append(line)
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
        cleaned.append(Page(page.source, page.page, text, page.ocr))
    return Document(doc.source, doc.doc_version, doc.superseded, cleaned)
