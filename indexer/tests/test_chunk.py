"""Stage 3 on the fixture corpus: metadata survives, headings are never orphaned, the
size limit holds and neighbours overlap (§3.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.chunk import chunk
from pipeline.clean import clean
from pipeline.extract import extract
from pipeline.models import Document, Page
from pipeline.run import discover

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def _fixture_chunks(size: int = 400, overlap: int = 50) -> list:
    out = []
    for path, version, superseded in discover(str(FIXTURES)):
        out.extend(chunk(clean(extract(str(path), version, superseded)), size, overlap))
    return out


def test_every_chunk_carries_all_metadata_fields() -> None:
    chunks = _fixture_chunks()
    assert chunks
    for c in chunks:
        assert set(c.metadata()) == {"source", "section", "page", "doc_version", "superseded"}
        assert c.section and c.page == 1 and c.doc_version in {"2023", "2026"}
    old = {c.superseded for c in chunks if c.source == "academic-rules-2023.md"}
    assert old == {True}


def test_sections_come_from_the_headings_and_never_lose_them() -> None:
    chunks = _fixture_chunks()
    sections = {(c.source, c.section) for c in chunks}
    assert ("academic-rules-2026.md", "2. Academic warning") in sections
    assert ("fees-2026.md", "1. Tuition") in sections
    for c in chunks:
        heading, _, body = c.text.partition("\n")
        assert heading == c.section and body.strip()


def test_a_table_stays_in_one_chunk_with_its_heading() -> None:
    tuition = [c for c in _fixture_chunks() if c.section == "1. Tuition"]
    assert len(tuition) == 1
    assert "| BS (all disciplines) | 10,000 |" in tuition[0].text


def _long_doc() -> Document:
    sentences = " ".join(f"Rule {i} applies to every student in the programme." for i in range(60))
    return Document("long.md", "2026", False,
                    [Page("long.md", 1, f"# 5. Long policy\n{sentences}"),
                     Page("long.md", 2, "Closing sentence on the second page.")])


def test_size_limit_holds_and_neighbours_overlap() -> None:
    chunks = chunk(_long_doc(), size=60, overlap=10)
    assert len(chunks) > 3
    for c in chunks:
        assert len(c.text.split()) <= 60
        assert c.text.startswith("5. Long policy\n")
    for a, b in zip(chunks, chunks[1:]):
        tail = a.text.split()[-10:]
        assert b.text.split()[3:13] == tail          # after the 3-word heading
    assert chunks[0].page == 1 and "Closing sentence" in chunks[-1].text   # page = where it starts
    assert [c.id for c in chunks] == [c.id for c in chunk(_long_doc(), 60, 10)]


def test_no_overlap_means_no_repeated_words() -> None:
    chunks = chunk(_long_doc(), size=60, overlap=0)
    stored = sum(len(c.text.split()) - 3 for c in chunks)
    original = sum(len(p.text.split()) for p in _long_doc().pages) - 4  # minus "# ..." line
    assert stored == original


def test_a_sentence_longer_than_a_chunk_is_split_by_words() -> None:
    doc = Document("x.md", "1", False, [Page("x.md", 1, "# T\n" + "word " * 250)])
    assert all(len(c.text.split()) <= 100 for c in chunk(doc, 100, 0))


@pytest.mark.parametrize("size, overlap", [(100, 100), (100, -1)])
def test_bad_overlap_is_refused(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk(_long_doc(), size, overlap)
