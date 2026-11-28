"""Verification (RAGOps A1; paper 4.2.2): after extraction, before chunking.

Every document gets pass or fail, with a reason, for four checks:

    quality       the text exists and is readable: not empty, not garbled, extracted
    completeness  the catalog has source, title and version; the file has pages and is
                  not truncated
    recency       no newer version of the same document (doc_id) is in the lake
    uniqueness    no exact or near duplicate: a named slot, run by Member 2's check

A quality or completeness failure quarantines the document: it is not indexed. A recency
failure archives it: it stays indexed with superseded: true, so retrieval excludes it
unless a question asks for the older version, and it can be restored (A2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .lake import Entry, version_key
from .models import Document

QUARANTINE_CHECKS = ("quality", "completeness", "uniqueness")
# Words of three or more letters, the share of text a reader would recognise.
WORD = re.compile(r"[A-Za-z]{3,}")
SENTENCE_END = re.compile(r"""[.!?:;)\]"'|*_`>-]\s*$""")


@dataclass
class Check:
    name: str
    passed: bool | None          # None: the check did not run
    reason: str

    def row(self) -> dict[str, object]:
        return {"check": self.name,
                "result": {True: "pass", False: "fail", None: "not run"}[self.passed],
                "reason": self.reason}


def quality(doc: Document | None, error: str | None, min_words: int,
            max_garbled: float) -> Check:
    if doc is None:
        return Check("quality", False, f"extraction failed: {error}")
    text = "\n".join(p.text for p in doc.pages)
    words = len(text.split())
    if words < min_words:
        return Check("quality", False, f"only {words} words extracted (minimum {min_words})")
    readable = sum(len(w) for w in WORD.findall(text))
    letters = sum(c.isalnum() for c in text)
    garbled = 1 - readable / letters if letters else 1.0
    if garbled > max_garbled:
        return Check("quality", False, f"{garbled:.0%} of the text is not readable words "
                                       f"(maximum {max_garbled:.0%})")
    return Check("quality", True, f"{words} words, {garbled:.0%} unreadable")


def truncation(path: Path, doc: Document | None) -> str | None:
    """Why the file looks cut short, or None. PDFs end with %%EOF and HTML with </html>;
    a text file's last line should end a sentence, a table row or a heading."""
    suffix = path.suffix.lower()
    try:
        tail = path.read_bytes()[-2048:]
    except OSError as exc:
        return f"unreadable file: {exc}"
    if suffix == ".pdf":
        return None if b"%%EOF" in tail else "PDF has no %%EOF marker: the file is cut short"
    if suffix in (".html", ".htm"):
        return None if b"</html>" in tail.lower() else "HTML has no closing </html> tag"
    lines = [ln for ln in tail.decode("utf-8", "replace").splitlines() if ln.strip()]
    if not lines:
        return "the file is empty"
    last = lines[-1].strip()
    if last.startswith("#") or SENTENCE_END.search(last):
        return None
    return f"the text stops mid-sentence: ...{last[-40:]!r}"


def completeness(entry: Entry, path: Path, doc: Document | None) -> Check:
    missing = [name for name, value in (("source", entry.file), ("title", entry.title),
                                        ("date or version", entry.doc_version))
               if not str(value).strip() or str(value).strip().lower() == "unknown"]
    if doc is not None and not doc.pages:
        missing.append("page count")
    cut = truncation(path, doc)
    problems = ([f"missing metadata: {', '.join(missing)}"] if missing else []) + \
        ([cut] if cut else [])
    if problems:
        return Check("completeness", False, "; ".join(problems))
    pages = len(doc.pages) if doc else 0
    return Check("completeness", True, f"source, title, version {entry.doc_version}, "
                                       f"{pages} page(s), not truncated")


def recency(entry: Entry, lake_entries: list[Entry]) -> Check:
    """Fails when a newer version of the same doc_id is among `lake_entries`, which the
    run passes as the current (raw/) versions only, so a rollback holds."""
    newer = [e for e in lake_entries
             if e.doc_id == entry.doc_id and e.file != entry.file
             and version_key(e.doc_version) > version_key(entry.doc_version)]
    if newer:
        best = max(newer, key=lambda e: version_key(e.doc_version))
        return Check("recency", False, f"newer version {best.doc_version} of "
                                       f"{entry.doc_id!r} exists ({best.file})")
    return Check("recency", True, f"latest version of {entry.doc_id!r}")


def uniqueness_not_run() -> Check:
    return Check("uniqueness", None,
                 "not run yet: exact and near-duplicate detection is Member 2's swap task "
                 "(docs/planning/ragops-implementation-plan.md)")


def decide(checks: list[Check]) -> str:
    """index, archive (indexed as superseded) or quarantine (not indexed)."""
    if any(c.passed is False for c in checks if c.name in QUARANTINE_CHECKS):
        return "quarantine"
    if any(c.name == "recency" and c.passed is False for c in checks):
        return "archive"
    return "index"


def table(rows: list[dict]) -> str:
    """The per-run report as a fixed-width table, for the Job's log and screenshots."""
    names = ("quality", "completeness", "recency", "uniqueness")
    head = f"{'document':44} " + " ".join(f"{n:12}" for n in names) + " action"
    out = [head, "-" * len(head)]
    for r in rows:
        results = {c["check"]: c["result"] for c in r["checks"]}
        out.append(f"{r['file'][:44]:44} " + " ".join(f"{results.get(n, '-'):12}" for n in names)
                   + f" {r['action']}")
        out += [f"    {c['check']}: {c['reason']}" for c in r["checks"] if c["result"] == "fail"]
    return "\n".join(out)
