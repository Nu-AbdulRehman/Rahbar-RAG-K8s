"""RAGOps A1: each verification check, and what its result does to the document."""

from __future__ import annotations

from pathlib import Path

from pipeline.lake import Entry
from pipeline.models import Document, Page
from pipeline.verify import (
    Check,
    Duplicates,
    completeness,
    decide,
    quality,
    recency,
    text_hash,
    truncation,
    windows,
)

from conftest import bag_of_words


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
    unique = Check("uniqueness", None, "not run")
    assert decide([Check("quality", True, ""), Check("recency", True, ""), unique]) == "index"
    assert decide([Check("quality", False, ""), Check("recency", True, ""), unique]) == "quarantine"
    assert decide([Check("completeness", False, ""), unique]) == "quarantine"
    assert decide([Check("recency", False, ""), unique]) == "archive"
    # a quarantine wins over an archive: a broken old version is not indexed at all
    assert decide([Check("quality", False, ""), Check("recency", False, "")]) == "quarantine"
    assert ok.passed and not bad.passed
    assert decide([Check("uniqueness", False, "exact duplicate"), Check("recency", True, "")]) \
        == "quarantine"


EXAM = ("A student must reach the examination hall at least ten minutes before the paper "
        "starts and carry the student card. Mobile phones, smart watches, notes and bags are "
        "not allowed at the seat. Copying or talking is an unfair means case. ") * 3
EXAM_REWORDED = EXAM.replace("starts", "begins").replace("talking", "speaking")
LIBRARY = ("The library opens at eight in the morning. Books are lent for fourteen days and "
           "a late return costs a fine per day. Reference books stay in the reading room. ") * 3


def _finder(calls: list[int] | None = None, threshold: float = 0.9,
            cache: Path | None = None) -> Duplicates:
    def embed(texts: list[str]) -> list[list[float]]:
        if calls is not None:
            calls.append(len(texts))
        return bag_of_words(texts)
    return Duplicates(threshold, embed, "fake-model", cache)


def _first(finder: Duplicates, entry: Entry, text: str) -> Check:
    check, record = finder.check(entry, _doc(text))
    finder.remember(record)
    return check


def test_uniqueness_fails_an_exact_copy_and_names_the_original() -> None:
    finder = _finder()
    assert _first(finder, _entry(file="b03.md", doc_id="exam"), EXAM).passed is True
    copy = _first(finder, _entry(file="b04.md", doc_id="exam"), EXAM)
    assert copy.passed is False
    assert "exact duplicate of b03.md" in copy.reason
    # the same text with other whitespace is still the same document
    assert text_hash(_doc(EXAM)) == text_hash(_doc(EXAM.replace(" ", "\n  ")))


def test_uniqueness_fails_a_near_duplicate_only_above_the_threshold() -> None:
    finder = _finder(threshold=0.9)
    _first(finder, _entry(file="b03.md", doc_id="exam"), EXAM)
    near = _first(finder, _entry(file="b05.md", doc_id="exam-notice"), EXAM_REWORDED)
    assert near.passed is False and "near duplicate of b03.md" in near.reason
    other = _first(finder, _entry(file="b01.md", doc_id="library"), LIBRARY)
    assert other.passed is True and "closest" in other.reason
    # the same pair under a threshold above its cosine passes: the number decides
    strict = _finder(threshold=0.9999)
    _first(strict, _entry(file="b03.md", doc_id="exam"), EXAM)
    assert _first(strict, _entry(file="b05.md", doc_id="exam-notice"),
                  EXAM_REWORDED).passed is True


def test_versions_of_one_document_are_left_to_the_recency_check() -> None:
    finder = _finder(threshold=0.5)
    _first(finder, _entry(file="fees-2026.md", doc_id="fees", doc_version="2026"), EXAM)
    newer = _first(finder, _entry(file="fees-2027.md", doc_id="fees", doc_version="2027"),
                   EXAM_REWORDED)
    assert newer.passed is True
    # same doc_id and the same version in another file is a copy, so it is compared
    again = _first(finder, _entry(file="fees-copy.md", doc_id="fees", doc_version="2027"),
                   EXAM_REWORDED + " extra")
    assert again.passed is False


def test_a_rejected_document_is_never_the_original() -> None:
    finder = _finder()
    _first(finder, _entry(file="b03.md", doc_id="exam"), EXAM)
    check, record = finder.check(_entry(file="b04.md", doc_id="exam"), _doc(EXAM))
    assert record is None                    # nothing to remember for a failed check
    assert len(finder.accepted) == 1


def test_document_vectors_are_cached_so_an_unchanged_corpus_embeds_nothing(
        tmp_path: Path) -> None:
    cache, calls = tmp_path / "signatures.json", []
    first = _finder(calls, cache=cache)
    _first(first, _entry(file="b03.md", doc_id="exam"), EXAM)
    first.save()
    assert calls and first.embedded == sum(calls)
    calls.clear()
    second = _finder(calls, cache=cache)
    assert _first(second, _entry(file="b03.md", doc_id="exam"), EXAM).passed is True
    assert calls == [] and second.embedded == 0


def test_windows_spread_over_a_long_document_and_cap_the_embedding_calls() -> None:
    long = " ".join(f"w{i}" for i in range(10_000))
    parts = windows(_doc(long), size=300, most=8)
    assert len(parts) == 8
    assert parts[0].startswith("w0 ") and "w9999" in parts[-1]
    assert windows(_doc("short text"), size=300, most=8) == ["short text"]
