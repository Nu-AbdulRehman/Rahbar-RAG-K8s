"""Stage 2: headers, footers, page numbers and contents go; headings and clause numbers stay."""

from __future__ import annotations

from pipeline.clean import clean
from pipeline.models import Document, Page

TOPICS = ["Fees", "Labs", "Exams", "Grades", "Repeats", "Withdrawals"]


def _doc(texts: list[str]) -> Document:
    return Document("rules.pdf", "2026-06", False,
                    [Page("rules.pdf", i + 1, t) for i, t in enumerate(texts)])


def test_running_headers_and_page_numbers_are_removed() -> None:
    pages = [f"NATIONAL UNIVERSITY\n# {topic}\n{i}.1 {topic} follow the rules.\n"
             f"U ndergraduate Rules 2026 {i}\n{i}" for i, topic in enumerate(TOPICS, 1)]
    cleaned = clean(_doc(pages))
    assert cleaned.pages[0].text == "# Fees\n1.1 Fees follow the rules."
    assert all("NATIONAL" not in p.text and "ndergraduate" not in p.text
               for p in cleaned.pages)
    assert [p.page for p in cleaned.pages] == [1, 2, 3, 4, 5, 6]


def test_contents_entries_go_but_the_body_heading_stays() -> None:
    toc = "# Table of Contents\n# Attendance Requirements 4\nAcademic Year........ 1"
    body = "# Attendance Requirements\n1.21 Students are required to attend."
    cleaned = clean(_doc([toc, body]))
    assert cleaned.pages[0].text == ""
    assert cleaned.pages[1].text == body


def test_lone_clause_numbers_survive_even_when_repeated() -> None:
    pages = [f"6.{i}\n\n{topic} follow the summer rules." for i, topic in enumerate(TOPICS, 1)]
    assert clean(_doc(pages)).pages[0].text.startswith("6.1")
