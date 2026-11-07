"""Stage 1 on the fixture corpus and small synthetic inputs (§3.1). No tesseract needed:
the OCR call is replaced, so the test checks that a page with no text layer is sent to OCR."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from pipeline.extract import extract, html_text, is_heading, mark_ocr_headings

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def test_markdown_keeps_headings_and_drops_front_matter() -> None:
    doc = extract(str(FIXTURES / "academic-rules-2026.md"), "2026", False)
    text = doc.pages[0].text
    assert "doc_version" not in text
    assert "# 1. Attendance" in text.split("\n")
    assert doc.source == "academic-rules-2026.md" and doc.pages[0].page == 1


def test_html_table_rows_keep_their_cells_together() -> None:
    html = ("<nav>Home</nav><h2>Fee Refund Policy</h2><p>Refunds follow HEC rules.</p>"
            "<table><tr><th>Timeline</th><th>Refund</th></tr>"
            "<tr><td>Upto 15th day</td><td>80%</td></tr></table><script>x()</script>")
    text = html_text(html)
    assert "# Fee Refund Policy" in text
    assert "| Timeline | Refund |\n| Upto 15th day | 80% |" in text
    assert "Home" not in text and "x()" not in text


@pytest.mark.parametrize("line, larger, expected", [
    ("Attendance Requirements", True, True),
    ("Transfer to another FAST-NUCES campus", True, True),
    ("6. Rules for Summer Semester", False, True),
    ("5. Unacceptable Uses of Generative AI Tools", False, True),
    ("1. The University takes pride in maintaining a peaceful, and", False, False),
    ("1.21 Students are required to maintain 100% attendance", False, False),
    ("I V", True, False),
    ("1. BBA X X X X", True, False),
])
def test_heading_rules(line: str, larger: bool, expected: bool) -> None:
    assert is_heading(line, larger) is expected


def test_ocr_headings_are_standalone_title_lines() -> None:
    text = "Attendance Requirements\n\n1.21 Students are required to\nattend.\n\nDads\n\nScope"
    out = mark_ocr_headings(text).split("\n\n")
    assert out[0] == "# Attendance Requirements"
    assert out[1].startswith("1.21")
    assert out[2] == "Dads"            # one short word: a misread clause number
    assert out[3] == "# Scope"


def test_a_page_with_no_text_layer_is_ocrd(tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = tmp_path / "scan.pdf"
    with pdf.open("wb") as fh:
        writer.write(fh)
    fake = types.SimpleNamespace(image_to_string=lambda image: "Scope\n\nThe policy covers.")
    monkeypatch.setitem(sys.modules, "pytesseract", fake)

    doc = extract(str(pdf), "2022-05", False, ocr_dpi=50)
    assert doc.pages[0].ocr is True
    assert doc.pages[0].text == "# Scope\n\nThe policy covers."
