"""Stage 1: Extract. PDF, HTML or Markdown to text, page by page.

Every format comes out the same way, so the later stages need no format logic:
headings are lines starting with "# ", table rows are lines starting with "| ",
and paragraphs are separated by blank lines.
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .models import Document, Page

MIN_TEXT_CHARS = 20          # a page with less text than this has no usable text layer
HEADING_SIZE_STEP = 1.5      # points above the body font size that make a line a heading
MAX_HEADING_WORDS = 12
# "6. Rules for Summer Semester", "XI. Policy on Retake Examination": numbered headings
# set in the body font, as in the Student Handbook's Generative AI policy.
NUMBERED_HEADING = re.compile(r"^(\d{1,2}|[IVX]{1,5})\.\s+[A-Z][^.]{2,80}$")


def extract(path: str, doc_version: str, superseded: bool, ocr_dpi: int = 300) -> Document:
    """Return the document's text page by page.

    Pages with no text layer are rendered and OCR'd, and marked ocr=True.
    """
    file = Path(path)
    suffix = file.suffix.lower()
    if suffix == ".pdf":
        pages = _pdf_pages(file, ocr_dpi)
    elif suffix in (".html", ".htm"):
        html = file.read_text(encoding="utf-8", errors="replace")
        pages = [Page(file.name, 1, html_text(html))]
    else:
        pages = [Page(file.name, 1, _markdown_text(file.read_text(encoding="utf-8")))]
    return Document(source=file.name, doc_version=doc_version, superseded=superseded,
                    pages=pages)


# --- PDF ----------------------------------------------------------------------------------

def _pdf_pages(file: Path, ocr_dpi: int) -> list[Page]:
    import pdfplumber

    pages: list[Page] = []
    with pdfplumber.open(file) as pdf:
        # Crop to the page box: the handbook PDFs carry the facing page's text at
        # negative x, which would otherwise duplicate every clause (docs/PIPELINE.md).
        cropped = [p.within_bbox(p.bbox) for p in pdf.pages]
        lines = [p.extract_text_lines(return_chars=True) for p in cropped]
        body = _body_size(lines)
        for number, (page, page_lines) in enumerate(zip(cropped, lines), start=1):
            text = "\n".join(_mark_heading(line, body) for line in page_lines)
            if len(text.strip()) >= MIN_TEXT_CHARS:
                pages.append(Page(file.name, number, text))
            else:
                pages.append(Page(file.name, number, ocr_page(page, ocr_dpi), ocr=True))
    return pages


def _size(line: dict[str, Any]) -> float:
    sizes = Counter(round(c["size"], 1) for c in line["chars"] if c["text"].strip())
    return sizes.most_common(1)[0][0] if sizes else 0.0


def _body_size(pages: list[list[dict[str, Any]]]) -> float:
    counts: Counter[float] = Counter()
    for page in pages:
        for line in page:
            counts[_size(line)] += len(line["text"])
    return counts.most_common(1)[0][0] if counts else 0.0


SMALL_WORDS = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the",
               "to", "with"}


def is_heading(text: str, larger: bool) -> bool:
    """A heading is short and either set larger than the body text, or numbered like a
    chapter and title-like ("6. Rules for Summer Semester"). Title-likeness rejects wrapped
    list items in the body font ("1. The University takes pride in ...")."""
    words = text.split()
    if not words or len(words) > MAX_HEADING_WORDS or text.endswith((",", ";")) or "|" in text:
        return False
    alpha = [w for w in words if w[0].isalpha()]
    if not any(sum(c.isalpha() for c in w) >= 3 for w in alpha):
        return False            # "I V", "X X X": page numerals and table ticks
    if sum(len(w) == 1 for w in words) > len(words) / 2:
        return False
    if larger:
        return True             # the font already says so ("Transfer to another ... campus")
    content = [w for w in alpha if w.lower() not in SMALL_WORDS]
    if content and sum(w[0].isupper() for w in content) < 0.6 * len(content):
        return False
    return bool(NUMBERED_HEADING.match(text))


def _mark_heading(line: dict[str, Any], body: float) -> str:
    text = " ".join(line["text"].split())
    return f"# {text}" if is_heading(text, _size(line) >= body + HEADING_SIZE_STEP) else text


def ocr_page(page: Any, dpi: int) -> str:
    """Render one pdfplumber page with pypdfium2 (installed with pdfplumber, so no
    poppler needed) and OCR it with tesseract."""
    import pytesseract

    image = page.to_image(resolution=dpi).original.convert("L")
    return mark_ocr_headings(pytesseract.image_to_string(image))


def mark_ocr_headings(text: str) -> str:
    """A scan has no fonts, so guess headings from the text: a short, title-like line
    standing alone between blank lines. Tesseract separates paragraphs with blank lines."""
    out = []
    for block in re.split(r"\n\s*\n", text):
        line = " ".join(block.split())
        words = line.split()
        title_like = (bool(words) and line[0].isupper()
                      and not line.endswith((".", ":"))
                      and not re.match(r"^\d+\.\d+", line)
                      # one-word OCR fragments ("Dads", "DD") are misread clause numbers
                      and (len(words) > 1 or sum(c.isalpha() for c in line) >= 5))
        if "\n" not in block.strip() and title_like and is_heading(line, larger=True):
            out.append(f"# {line}")
        elif block.strip():
            out.append(block.strip())
    return "\n\n".join(out)


# --- HTML ---------------------------------------------------------------------------------

class _HtmlToText(HTMLParser):
    """Headings become "# " lines and table rows become "| a | b |" lines, so a fee stays
    in the same row as its label. Script, style, nav, header and footer are dropped."""

    SKIP = {"script", "style", "nav", "header", "footer", "noscript", "head"}
    BLOCK = {"p", "div", "li", "br", "ul", "ol", "section", "article", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.skip += 1
        elif self.skip:
            return
        elif re.fullmatch(r"h[1-6]", tag):
            self.out.append("\n\n# ")
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif tag in self.BLOCK:
            self.out.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif self.skip:
            return
        elif re.fullmatch(r"h[1-6]", tag) or tag in self.BLOCK:
            self.out.append("\n\n")
        elif tag in ("td", "th") and self.row is not None and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.out.append("\n| " + " | ".join(self.row) + " |\n")
            self.row = None

    def handle_data(self, data: str) -> None:
        if self.skip or not data.strip():
            return
        if self.cell is not None:
            self.cell.append(data)
        else:
            self.out.append(" ".join(data.split()) + " ")


def html_text(html: str) -> str:
    parser = _HtmlToText()
    parser.feed(html)
    lines = [" ".join(line.split()) for line in "".join(parser.out).split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n\n(\| .*\|)\n(?=\n\| )", r"\n\n\1", text)   # keep table rows together
    text = re.sub(r"(\|)\n\n(?=\| )", r"\1\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --- Markdown and text ------------------------------------------------------------------

def _markdown_text(text: str) -> str:
    """The fixtures start with '---' front matter, which run.discover() already read."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return re.sub(r"^#{1,6}\s+", "# ", text.strip(), flags=re.M)
