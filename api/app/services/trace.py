"""The trace record (RAGOps D1, F4): one JSON line per query.

Every /api/ask writes one record, built step by step by services/answer.py:

    trace_id, timestamp, pod          the request id is the trace id
    query, rewritten_query            the question, and the standalone query a follow-up
                                      was retrieved with (null when not a follow-up)
    embedding                         model, version (Ollama digest), dimension
    collection                        the Chroma collection searched
    retrieval                         top_k, filters (superseded metadata filter, relevance
                                      floor), every chunk with doc_id, doc_version,
                                      superseded, content_hash and score, the reranker
                                      (none) and the order the evidence went into the prompt
    generation                        provider, model, parameters, prompt_hash, attempts,
                                      fallback, tokens
    response                          answer, citations, answered_from_context, confidence
    guardrails                        every guardrail action on this query (guardrails.py,
                                      generation.py)
    latency_ms                        per stage: cache, embed, retrieve, generate, summary,
                                      total
    cache                             hit | miss | skipped, similarity, stored

Two copies, as ADR 0005 decides:
- standard output, through the "rahbar.trace" logger at INFO: the record above, readable
  with `kubectl logs` (F4). No prompt text and no passage text: ADR 0004 still keeps those
  out of INFO logs.
- TRACE_DIR (the ragops-results volume on the cluster): the same record plus the full
  prompt, the evidence passages and the conversation block, appended to
  traces-<date>-<pod>.jsonl. One file per pod, so three replicas never interleave lines.
  scripts/trace_show.py rebuilds the prompt from it (D2).

A trace never holds a secret: no key, no header, no environment. Writing it never fails
the request: a full or missing volume is logged and counted, and the answer still goes out.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from ..providers.llm.base import Prompt
from ..routes import metrics
from ..schemas import Passage

log = logging.getLogger("rahbar.trace")

# Keys that only the volume copy carries (ADR 0004: never at INFO).
VOLUME_ONLY = ("prompt", "evidence", "conversation")


def prompt_hash(prompt: Prompt) -> str:
    """SHA-256 of exactly what the model received: system message, a blank line, user
    message. trace_show.py recomputes it from the rebuilt prompt."""
    return hashlib.sha256(f"{prompt.system}\n\n{prompt.user}".encode()).hexdigest()


def chunk_row(rank: int, p: Passage, floor: float) -> dict[str, Any]:
    return {"rank": rank, "chunk_id": p.chunk_id, "doc_id": p.doc_id,
            "doc_version": p.doc_version, "superseded": p.superseded,
            "content_hash": p.content_hash, "source": p.source, "section": p.section,
            "page": p.page, "score": p.score, "above_floor": p.score >= floor}


def evidence_row(p: Passage) -> dict[str, Any]:
    return {"chunk_id": p.chunk_id, "source": p.source, "section": p.section, "page": p.page,
            "score": p.score, "text": p.text}


class TraceSink:
    """Where finished records go: stdout always, the trace volume when TRACE_DIR is set."""

    def __init__(self, trace_dir: str = "", pod: str = "-") -> None:
        self.dir = Path(trace_dir) if trace_dir else None
        self.pod = pod

    def path(self, day: str) -> Path | None:
        return None if self.dir is None else self.dir / f"traces-{day}-{self.pod}.jsonl"

    def write(self, record: dict[str, Any]) -> None:
        public = {k: v for k, v in record.items() if k not in VOLUME_ONLY}
        log.info("trace", extra=public)
        path = self.path(record["timestamp"][:10])
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            metrics.TRACE_WRITE_FAILURES.inc()
            log.warning("trace not written to the volume", extra={"error": type(exc).__name__,
                                                                  "trace_dir": str(self.dir)})


def now() -> str:
    """UTC, millisecond precision: trace_summary.py windows on it."""
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t % 1 * 1000):03d}Z"
