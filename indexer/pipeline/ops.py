"""Data lake operations for the RAGOps A2 demos.

    python -m pipeline.ops counts                    chunks per document in the collection
    python -m pipeline.ops status                    every catalog entry and where it lives
    python -m pipeline.ops restore <doc_id> <ver>    roll a superseded version back
    python -m pipeline.ops similarities [--top N]    document cosine for every pair in the
                                                     lake (incoming/ too): the data the
                                                     near-duplicate threshold comes from

restore only moves files and rewrites the catalog; the next ingestion run (the only writer
to Chroma, decision R9) flips the superseded metadata, without re-embedding.
"""

from __future__ import annotations

import argparse
import sys

from .config import IndexerSettings, get_settings
from .lake import Lake


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.ops")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("counts", help="chunks per doc_id in the collection")
    sub.add_parser("status", help="catalog entries and their location")
    restore = sub.add_parser("restore", help="make an archived version current again")
    restore.add_argument("doc_id")
    restore.add_argument("version")
    sims = sub.add_parser("similarities", help="pairwise document cosine (uniqueness)")
    sims.add_argument("--top", type=int, default=15, help="pairs to print, highest first")
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
    if args.command == "similarities":
        return similarities(settings, lake, args.top)
    back, displaced = lake.restore(args.doc_id, args.version)
    print(f"restored {back.doc_id} {back.doc_version} ({back.file}) as current")
    for e in displaced:
        print(f"archived {e.doc_id} {e.doc_version} ({e.file})")
    print("run the ingestion Job to apply it to the index (metadata only, no re-embedding)")
    return 0


def similarities(settings: IndexerSettings, lake: Lake, top: int) -> int:
    """Pairwise cosine of document embeddings (VERIFY_EMBED_MODEL) over raw/, archive/
    and incoming/, so the threshold can be chosen before a batch is ingested. Pairs that
    are versions of one document are marked: the check skips them."""
    from dataclasses import replace

    from .embed import embed
    from .extract import extract
    from .lake import read_folder
    from .verify import similarity_matrix

    entries = [(lake.path(e), e) for e in lake.current()]
    entries += [(lake.incoming / e.file, e) for e in read_folder(lake.incoming)]
    docs, ids = {}, {}
    for path, entry in entries:
        try:
            docs[entry.file] = extract(str(path), entry.doc_version, False, settings.ocr_dpi)
            ids[entry.file] = (entry.doc_id, entry.doc_version)
        except Exception as exc:  # a corrupt file has no embedding; verification says why
            print(f"skipped {entry.file}: {type(exc).__name__}")
    verify = replace(settings, embed_model=settings.verify_embed_model)
    pairs = similarity_matrix(docs, lambda texts: embed(texts, verify))
    print(f"{len(docs)} documents, {len(pairs)} pairs, model {settings.verify_embed_model}, "
          f"threshold VERIFY_NEAR_DUPLICATE={settings.verify_near_duplicate}")
    for cosine, a, b in pairs[:top]:
        version = ids[a][0] == ids[b][0] and ids[a][1] != ids[b][1]
        print(f"  {cosine:.4f}  {a}  ~  {b}" + ("   (versions of one doc_id: skipped)"
                                                 if version else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
