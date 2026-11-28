"""Write b06-scholarship-policy-truncated.pdf: a real one-page PDF of our own text, cut
short the way an interrupted download is (Batch B's truncated file, RAGOps A2).

    python corpus/batch_b/make_truncated_pdf.py
"""

from __future__ import annotations

from pathlib import Path

LINES = [
    "Merit Scholarship Policy (2026-27)",
    "1. Students in the top five percent of their batch by semester GPA receive a",
    "fifty percent tuition waiver for the next semester.",
    "2. A student must carry at least fifteen credit hours to remain eligible.",
    "3. The waiver is withdrawn if the student is found guilty of an unfair means case.",
]


def pdf_bytes(lines: list[str]) -> bytes:
    text = "BT /F1 11 Tf 50 760 Td 14 TL " + " ".join(
        f"({ln.replace('(', '[').replace(')', ']')}) '" for ln in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return out


if __name__ == "__main__":
    whole = pdf_bytes(LINES)
    cut = whole[: int(len(whole) * 0.55)]          # stops inside the page content stream
    target = Path(__file__).with_name("b06-scholarship-policy-truncated.pdf")
    target.write_bytes(cut)
    print(f"{target.name}: {len(cut)} of {len(whole)} bytes, no %%EOF")
