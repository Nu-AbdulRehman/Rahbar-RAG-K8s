"""Data lake operations for the RAGOps A2 demos.

    python -m pipeline.ops counts                    chunks per document in the collection
    python -m pipeline.ops status                    every catalog entry and where it lives
    python -m pipeline.ops restore <doc_id> <ver>    roll a superseded version back

restore only moves files and rewrites the catalog; the next ingestion run (the only writer
to Chroma, decision R9) flips the superseded metadata, without re-embedding.
"""

from __future__ import annotations

import argparse
import sys

from .config import get_settings
from .lake import Lake


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.ops")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("counts", help="chunks per doc_id in the collection")
    sub.add_parser("status", help="catalog entries and their location")
    restore = sub.add_parser("restore", help="make an archived version current again")
    restore.add_argument("doc_id")
    restore.add_argument("version")
    args = parser.parse_args(argv)
    settings = get_settings()
    lake = Lake(settings.data_lake_dir, settings.corpus_dir)

    if args.command == "counts":
        from .store import chunk_counts

        counts = chunk_counts(settings)
        width = max((len(k) for k in counts), default=8)
        print(f"collection {settings.collection}: {sum(counts.values())} chunks")
        for doc_id, n in counts.items():
            print(f"  {doc_id:{width}}  {n}")
        return 0
    if args.command == "status":
        for e in sorted(lake.catalog(), key=lambda e: (e.location, e.doc_id, e.doc_version)):
            flag = "superseded" if e.superseded else "current"
            print(f"  {e.location:10} {e.doc_id:40} {e.doc_version:10} {flag:10} {e.file}")
        return 0
    back, displaced = lake.restore(args.doc_id, args.version)
    print(f"restored {back.doc_id} {back.doc_version} ({back.file}) as current")
    for e in displaced:
        print(f"archived {e.doc_id} {e.doc_version} ({e.file})")
    print("run the ingestion Job to apply it to the index (metadata only, no re-embedding)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
