"""The indexer Job's entry point. It runs once and exits (section 4.2).

    python -m pipeline.run --dummy    # week 1: three fake chunks, no model needed
    python -m pipeline.run            # the real pipeline: extract, clean, chunk, embed, store

Exit code 0 means the index was written and the semantic cache expired; anything else
fails the Job, and Kubernetes retries it up to the Job's backoffLimit.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .config import IndexerSettings, get_settings
from .invalidate import invalidate_cache
from .models import Chunk


def log(msg: str, **fields: object) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "logger": "rahbar.indexer", "msg": msg, **fields}), flush=True)


def _front_matter(path: Path) -> dict[str, str]:
    """Read `key: value` lines between leading '---' markers (used by eval/fixtures)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def discover(corpus_dir: str) -> list[tuple[Path, str, bool]]:
    """List (path, doc_version, superseded) for every document to index.

    corpus/fetch.py writes _index.json next to the files it downloads; use it when
    present. Otherwise read Markdown front matter (the CI fixtures work this way).
    """
    root = Path(corpus_dir)
    index = root / "_index.json"
    if index.exists():
        entries = json.loads(index.read_text(encoding="utf-8"))
        return [(root / e["file"], str(e.get("doc_version", "unknown")),
                 bool(e.get("superseded", False))) for e in entries]
    found = []
    for path in sorted(root.glob("*")):
        if path.suffix.lower() not in {".pdf", ".md", ".html", ".txt"}:
            continue
        if path.name.lower().startswith("readme"):
            continue
        meta = _front_matter(path) if path.suffix.lower() == ".md" else {}
        found.append((path, meta.get("doc_version", "unknown"),
                      meta.get("superseded", "false").lower() == "true"))
    return found


def run_pipeline(settings: IndexerSettings) -> int:
    """Ingest, verify, update the data lake, update the retrieval source (RAGOps A1, A2;
    paper Figure 3). Returns the number of chunks in the collection afterwards."""
    from .chunk import chunk
    from .clean import clean
    from .embed import embed
    from .extract import extract
    from .lake import Lake
    from .store import sync
    from .verify import completeness, decide, quality, recency, table, uniqueness_not_run

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    lake = Lake(settings.data_lake_dir, settings.corpus_dir)
    taken = lake.intake()
    changes = lake.refresh()
    log("data lake", run=run_id, intake=taken, **changes)
    entries = lake.current()
    if not entries:
        raise SystemExit(f"no documents found in {settings.corpus_dir}")

    # Recency compares with the current versions only: a newer version that was archived
    # on purpose (a rollback with pipeline.ops restore) must not re-archive the restored one.
    current = [e for e in entries if e.location == "raw"]
    rows: list[dict] = []
    all_chunks: list[Chunk] = []
    original_words = 0
    for entry in entries:
        path = lake.path(entry)
        try:
            doc = extract(str(path), entry.doc_version, entry.superseded, settings.ocr_dpi)
            doc.doc_id, doc.title, error = entry.doc_id, entry.title, None
        except Exception as exc:  # a corrupt file is a verification result, not a crash
            doc, error = None, f"{type(exc).__name__}: {exc}"
        checks = [quality(doc, error, settings.verify_min_words, settings.verify_max_garbled),
                  completeness(entry, path, doc), recency(entry, current),
                  uniqueness_not_run()]
        action = decide(checks)
        if action == "index" and entry.location == "archive":
            action = "archive"            # rolled back or superseded earlier: stays archived
        moved = None
        if action == "quarantine":
            moved = lake.quarantine(entry, [c.reason for c in checks if c.passed is False],
                                    run_id)
        elif action == "archive":
            moved = lake.archive(entry)
            entry.superseded = True
        rows.append({"file": entry.file, "doc_id": entry.doc_id, "version": entry.doc_version,
                     "checks": [c.row() for c in checks], "action": action, "file_move": moved})
        if action == "quarantine" or doc is None:
            continue
        doc.superseded = entry.superseded
        doc = clean(doc)
        pieces = chunk(doc, settings.chunk_size, settings.chunk_overlap)
        original_words += sum(len(p.text.split()) for p in doc.pages)
        log("chunked", source=entry.file, chunks=len(pieces), action=action,
            ocr_pages=sum(p.ocr for p in doc.pages))
        if not pieces:
            # Verified, yet nothing to index: a broken extract that the checks missed
            # (FAILURE-ANALYSIS.md, stage A). Fail the Job instead of silently shrinking.
            raise SystemExit(f"{entry.file} produced no chunks; refusing to index without it")
        all_chunks.extend(pieces)

    report = lake.write_report(f"verify-{run_id}.json", {"run": run_id, "documents": rows})
    print(table(rows), flush=True)
    log("verification", report=str(report), indexed=sum(r["action"] != "quarantine" for r in rows),
        quarantined=sum(r["action"] == "quarantine" for r in rows),
        archived=sum(r["action"] == "archive" for r in rows))
    if not all_chunks:
        raise SystemExit("every document failed verification; refusing to empty the index")
    stored_words = sum(len(c.text.split()) for c in all_chunks)
    log("chunking done", chunks=len(all_chunks), chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        storage_amplification=round(stored_words / max(original_words, 1), 3))
    result = sync(all_chunks, settings, lambda texts: embed(texts, settings))
    lake.write_report(f"ingest-{run_id}.json", {
        "run": run_id, "collection": settings.collection, "embed_model": settings.embed_model,
        "chunk_size": settings.chunk_size, "chunk_overlap": settings.chunk_overlap,
        "sync": asdict(result), "verification_report": report.name})
    log("store", collection=settings.collection, **asdict(result))
    return result.total


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the RAHBAR index, then exit.")
    parser.add_argument("--dummy", action="store_true", help="write three fake chunks")
    args = parser.parse_args()
    settings = get_settings()
    log("indexer starting", dummy=args.dummy, embed_model=settings.embed_model,
        collection=settings.collection, chroma=f"{settings.chroma_host}:{settings.chroma_port}",
        pod=settings.pod_name)
    started = time.perf_counter()
    try:
        if args.dummy:
            from .dummy import write_dummy_index
            from .store import get_client

            count = write_dummy_index(settings, get_client(settings))
        else:
            count = run_pipeline(settings)
    except NotImplementedError as exc:
        log("indexer stage not implemented yet", error=str(exc))
        return 2
    # Last step of every run, dummy included: the new index must not sit behind answers
    # cached from the old one (section 3.3). A Redis failure fails the Job, which retries.
    generation = invalidate_cache(settings)
    log("indexer finished", chunks=count, cache_generation=generation,
        seconds=round(time.perf_counter() - started, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
