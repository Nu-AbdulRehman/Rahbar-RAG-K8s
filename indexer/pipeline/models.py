"""The shapes passed between stages. Metadata fields are required (section 3.1)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class Page:
    """Text of one page, as extraction produced it."""

    source: str              # file name, e.g. Academic_Rules_Handbook_2026.pdf
    page: int                # 1-based
    text: str
    ocr: bool = False        # True when this page had no text layer and was OCR'd


@dataclass
class Document:
    source: str
    doc_version: str         # e.g. "2026-06"; from corpus/sources.yaml
    superseded: bool         # True for an older version of a policy
    pages: list[Page] = field(default_factory=list)
    doc_id: str = ""         # shared by every version of one document (RAGOps A1 recency)
    title: str = ""


@dataclass
class Chunk:
    id: str                  # stable: same document + same position gives the same id
    text: str
    source: str
    section: str             # the heading this chunk sits under, e.g. "5.4 Academic Warning"
    page: int
    doc_version: str
    superseded: bool
    doc_id: str = ""

    @property
    def content_hash(self) -> str:
        """What was embedded. Equal hashes mean the stored vector is still right, so an
        unchanged document is never embedded again (RAGOps A2)."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]

    def metadata(self) -> dict[str, str | int | bool]:
        """Chroma metadata values must be str, int, float or bool."""
        return {
            "source": self.source,
            "section": self.section,
            "page": self.page,
            "doc_version": self.doc_version,
            "superseded": self.superseded,
            "doc_id": self.doc_id or self.source,
            "content_hash": self.content_hash,
        }
