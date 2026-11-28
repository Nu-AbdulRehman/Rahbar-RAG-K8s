"""RAGOps A1: each verification check, and what its result does to the document."""

from __future__ import annotations

from pathlib import Path

from pipeline.lake import Entry
from pipeline.models import Document, Page
from pipeline.verify import (
    Check,
    completeness,
    decide,
    quality,
    recency,
    truncation,
    uniqueness_not_run,
)


def _doc(text: str, pages: int = 1) -> Document:
    return Document("a.md", "2026", False, [Page("a.md", i + 1, text) for i in range(pages)])


def _entry(**kw: object) -> Entry:
    base = {"file": "a.md", "doc_id": "a", "title": "A", "doc_version": "2026",
            "superseded": False}
    return Entry(**{**base, **kw})  # type: ignore[arg-type]


GOOD = "Students must attend at least eighty percent of lectures. " * 4


def test_quality_fails_empty_garbled_and_unextractable_text() -> None:
    assert quality(_doc(GOOD), None, 20, 0.3).passed is True
    empty = quality(_doc("  "), None, 20, 0.3)
    assert empty.passed is False and "0 words" in empty.reason
    garbled = quality(_doc("x9#k2 q7@z1 " * 40), None, 20, 0.3)
    assert garbled.passed is False and "not readable" in garbled.reason
    failed = quality(None, "PdfReadError: EOF marker not found", 20, 0.3)
    assert failed.passed is False and "extraction failed" in failed.reason


def test_completeness_reports_missing_metadata(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text(GOOD, encoding="utf-8")
    assert completeness(_entry(), path, _doc(GOOD)).passed is True
    missing = completeness(_entry(title="", doc_version="unknown"), path, _doc(GOOD))
    assert missing.passed is False
    assert "title" in missing.reason and "date or version" in missing.reason


def test_truncation_is_caught_per_format(tmp_path: Path) -> None:
    pdf = tmp_path / "cut.pdf"
    pdf.write_bytes(b"%PDF-1.7\n1 0 obj << >> endobj\n")         # no %%EOF: cut short
    assert truncation(pdf, None) is not None
    whole = tmp_path / "whole.pdf"
    whole.write_bytes(b"%PDF-1.7\n1 0 obj << >> endobj\n%%EOF\n")
    assert truncation(whole, None) is None
    text = tmp_path / "cut.md"
    text.write_text("# Fees\nThe refund for a withdrawal in the first week is", encoding="utf-8")
    assert "mid-sentence" in str(truncation(text, None))
    html = tmp_path / "cut.html"
    html.write_text("<html><body><table><tr><td>Rs. 12,000", encoding="utf-8")
    assert truncation(html, None) is not None


def test_recency_fails_only_the_older_version() -> None:
    old, new = _entry(file="r23.md", doc_version="2023-08"), _entry(file="r26.md",
                                                                   doc_version="2026-06")
    other = _entry(file="fees.md", doc_id="fees", doc_version="2027")
    lake = [old, new, other]
    assert recency(old, lake).passed is False and "2026-06" in recency(old, lake).reason
    assert recency(new, lake).passed is True
    assert recency(other, lake).passed is True


def test_decide_quarantines_on_quality_or_completeness_and_archives_on_recency() -> None:
    ok, bad = Check("x", True, ""), Check("x", False, "")
    unique = uniqueness_not_run()
    assert unique.passed is None
    assert decide([Check("quality", True, ""), Check("recency", True, ""), unique]) == "index"
    assert decide([Check("quality", False, ""), Check("recency", True, ""), unique]) == "quarantine"
    assert decide([Check("completeness", False, ""), unique]) == "quarantine"
    assert decide([Check("recency", False, ""), unique]) == "archive"
    # a quarantine wins over an archive: a broken old version is not indexed at all
    assert decide([Check("quality", False, ""), Check("recency", False, "")]) == "quarantine"
    assert ok.passed and not bad.passed
