"""Verification (RAGOps A1; paper 4.2.2): after extraction, before chunking.

Every document gets pass or fail, with a reason, for four checks:

    quality       the text exists and is readable: not empty, not garbled, extracted
    completeness  the catalog has source, title and version; the file has pages and is
                  not truncated
    recency       no newer version of the same document (doc_id) is in the lake
    uniqueness    no exact duplicate (SHA-256 of the extracted text) and no near duplicate
                  (cosine of document embeddings at or above VERIFY_NEAR_DUPLICATE) of a
                  document that was accepted before it

A quality, completeness or uniqueness failure quarantines the document: it is not indexed. A recency
failure archives it: it stays indexed with superseded: true, so retrieval excludes it
unless a question asks for the older version, and it can be restored (A2).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
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


def text_hash(doc: Document) -> str:
    """SHA-256 of the extracted text with whitespace collapsed: the same document saved
    twice, or re-saved with other line endings, hashes the same."""
    text = " ".join(" ".join(p.text for p in doc.pages).split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def windows(doc: Document, size: int = 300, most: int = 8) -> list[str]:
    """Up to `most` windows of `size` words, spread evenly over the document. Their mean
    embedding stands for the whole text, so two documents that share only a cover page or
    a header are not near duplicates, and a long PDF costs at most `most` embeddings."""
    words = " ".join(p.text for p in doc.pages).split()
    starts = list(range(0, max(len(words), 1), size))
    if len(starts) > most:
        step = (len(starts) - 1) / (most - 1)
        starts = [starts[round(i * step)] for i in range(most)]
    return [" ".join(words[s:s + size]) for s in starts if words[s:s + size]]


def _unit_mean(vectors: list[list[float]]) -> list[float]:
    mean = [sum(col) / len(vectors) for col in zip(*vectors)]
    norm = math.sqrt(sum(v * v for v in mean)) or 1.0
    return [v / norm for v in mean]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))          # both are unit vectors


@dataclass
class _Accepted:
    entry: Entry
    digest: str
    vector: list[float]


@dataclass
class Duplicates:
    """The uniqueness check (A1). Documents are checked in catalog order, so the one that
    was in the lake first is the original and a later copy is the duplicate.

    Only documents that end up indexed are remembered as originals: a document
    quarantined for another reason is never the original of anything.

    Versions of one document (same doc_id, another doc_version) are recency's business,
    not uniqueness's: a new fee schedule is meant to look like the old one. Two files
    with the same doc_id *and* version are compared, because that is a copy.

    Document vectors come from `embed_texts` (the model in VERIFY_EMBED_MODEL, which is
    fixed for every collection, so a candidate built with another EMBED_MODEL verifies
    the same way). They are kept in `cache_path` by text hash and model, so an unchanged
    corpus costs no embedding calls on the next run (A2)."""

    threshold: float
    embed_texts: Callable[[list[str]], list[list[float]]]
    model: str
    cache_path: Path | None = None
    accepted: list[_Accepted] = field(default_factory=list)
    _cache: dict[str, list[float]] | None = None
    embedded: int = 0          # embedding calls this run made (texts, not documents)

    def _vectors(self) -> dict[str, list[float]]:
        if self._cache is None:
            loaded: dict[str, list[float]] = {}
            if self.cache_path is not None and self.cache_path.exists():
                loaded = json.loads(self.cache_path.read_text(encoding="utf-8"))
            self._cache = loaded
        return self._cache

    def _vector(self, digest: str, doc: Document) -> list[float]:
        cache, key = self._vectors(), f"{self.model}:{digest}"
        if key not in cache:
            texts = windows(doc)
            cache[key] = _unit_mean(self.embed_texts(texts))
            self.embedded += len(texts)
        return cache[key]

    def save(self) -> None:
        if self.cache_path is not None and self._cache is not None:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache), encoding="utf-8")

    def check(self, entry: Entry, doc: Document | None) -> tuple[Check, _Accepted | None]:
        """The check's result, and the record to remember() if the document is indexed."""
        if doc is None:
            return Check("uniqueness", None, "not run: nothing was extracted"), None
        digest = text_hash(doc)
        for seen in self.accepted:
            if seen.digest == digest and seen.entry.file != entry.file:
                return Check("uniqueness", False,
                             f"exact duplicate of {seen.entry.file} "
                             f"(same SHA-256 {digest[:12]})"), None
        vector = self._vector(digest, doc)
        best: tuple[float, Entry] | None = None
        for seen in self.accepted:
            if seen.entry.doc_id == entry.doc_id and \
                    seen.entry.doc_version != entry.doc_version:
                continue                          # another version: the recency check's case
            similarity = _cosine(vector, seen.vector)
            if best is None or similarity > best[0]:
                best = (similarity, seen.entry)
        if best is not None and best[0] >= self.threshold:
            return Check("uniqueness", False,
                         f"near duplicate of {best[1].file} (cosine {best[0]:.3f} >= "
                         f"{self.threshold:.3f})"), None
        closest = f"closest {best[1].file} at {best[0]:.3f}" if best else "first document"
        return Check("uniqueness", True,
                     f"no duplicate ({closest}; threshold {self.threshold:.3f})"), \
            _Accepted(entry, digest, vector)

    def remember(self, record: _Accepted | None) -> None:
        if record is not None:
            self.accepted.append(record)


def similarity_matrix(docs: dict[str, Document],
                      embed_texts: Callable[[list[str]], list[list[float]]]) \
        -> list[tuple[float, str, str]]:
    """Every pair's cosine, highest first: the data the near-duplicate threshold is
    chosen from (python -m pipeline.ops similarities)."""
    vectors = {name: _unit_mean(embed_texts(windows(doc))) for name, doc in docs.items()}
    names = sorted(vectors)
    pairs = [(_cosine(vectors[a], vectors[b]), a, b)
             for i, a in enumerate(names) for b in names[i + 1:]]
    return sorted(pairs, reverse=True)


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
