"""Stage 5: Store. The only code in the whole system that writes to Chroma.

Re-indexing upserts into the live collection and then deletes the chunks that no longer
exist, so the API keeps serving the old index until the new one is complete, with no
empty-collection window (DECISIONS.md D15). The collection is rebuilt from scratch only
when its pinned embedding metadata changes, because vectors from two models (or two
dimensions) cannot share a collection.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import IndexerSettings
from .models import Chunk

DISTANCE = {"hnsw:space": "cosine"}    # Passage.score is 1 - cosine distance in the API


def get_client(settings: IndexerSettings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                               settings=ChromaSettings(anonymized_telemetry=False))


def pin_metadata(settings: IndexerSettings, dimension: int) -> dict[str, str | int]:
    """The embedding pin recorded on the collection (section 4.4): the model name and the
    vector dimension, which the API compares with its own EMBED_MODEL before it becomes
    ready."""
    return {"embed_model": settings.embed_model, "dimension": dimension}


def _pin(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (metadata or {}).items() if not k.startswith("hnsw:")}


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings,
          client: Any = None) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model
    and vector dimension in the collection metadata (section 4.4). Return the count."""
    if not chunks or len(chunks) != len(vectors):
        raise ValueError(f"refusing to store {len(chunks)} chunks with {len(vectors)} vectors")
    ids = [c.id for c in chunks]
    if len(set(ids)) != len(ids):
        raise ValueError("chunk ids are not unique")
    client = client or get_client(settings)
    pin = pin_metadata(settings, len(vectors[0]))

    collection = client.get_or_create_collection(settings.collection,
                                                 metadata={**DISTANCE, **pin})
    if _pin(collection.metadata) != pin:
        # A different model or dimension: the old vectors are not comparable. The API is
        # already not-ready on the pin mismatch, so this rebuild costs no correct answers.
        client.delete_collection(settings.collection)
        collection = client.create_collection(settings.collection,
                                              metadata={**DISTANCE, **pin})

    # ponytail: one upsert call; batch it if the corpus outgrows Chroma's max batch size.
    collection.upsert(ids=ids, documents=[c.text for c in chunks], embeddings=vectors,
                      metadatas=[c.metadata() for c in chunks])
    stale = set(collection.get(include=[])["ids"]) - set(ids)
    if stale:
        collection.delete(ids=sorted(stale))
    return int(collection.count())


@dataclass
class SyncResult:
    """What an incremental run did (RAGOps A2); printed and written to the ingest report."""

    embedded: int          # new or changed text: embedded and upserted
    metadata_updated: int  # same text, new metadata (a version flipped): no embedding
    unchanged: int
    deleted: int           # chunks whose document or position is gone: no orphans
    total: int             # chunks in the collection afterwards
    rebuilt: bool          # the embedding pin changed, so every chunk was embedded again


def _existing(client: Any, settings: IndexerSettings) -> Any:
    try:
        return client.get_collection(settings.collection)
    except Exception:  # chroma raises a NotFound-style error for a missing collection
        return None


def sync(chunks: list[Chunk], settings: IndexerSettings,
         embed_texts: Callable[[list[str]], list[list[float]]], client: Any = None) -> SyncResult:
    """Make the collection equal to `chunks`, embedding only what changed (RAGOps A2).

    A chunk is re-embedded when its id is new or its content_hash differs from the stored
    one; same text with different metadata (a superseded flag flipped by an archive or a
    restore) is updated in place; ids no longer produced are deleted, so a deleted or
    shortened document leaves no orphan chunks. A change of embedding model or dimension
    still rebuilds the collection, as store() does (section 4.4)."""
    if not chunks:
        raise ValueError("refusing to sync an empty set of chunks")
    ids = [c.id for c in chunks]
    if len(set(ids)) != len(ids):
        raise ValueError("chunk ids are not unique")
    client = client or get_client(settings)
    collection = _existing(client, settings)
    if collection is not None and _pin(collection.metadata).get("embed_model") \
            not in (None, settings.embed_model):
        collection = None                                # another model: nothing is reusable
    have: dict[str, dict[str, Any]] = {}
    if collection is not None:
        got = collection.get(include=["metadatas"])
        have = dict(zip(got["ids"], got["metadatas"]))

    to_embed = [c for c in chunks if have.get(c.id, {}).get("content_hash") != c.content_hash]
    vectors = embed_texts([c.text for c in to_embed]) if to_embed else []
    dimension = len(vectors[0]) if vectors else int(_pin(collection.metadata)["dimension"])
    pin = pin_metadata(settings, dimension)

    rebuilt = collection is None or _pin(collection.metadata) != pin
    if rebuilt:
        if collection is not None or settings.collection in _names(client):
            client.delete_collection(settings.collection)
        if len(to_embed) < len(chunks):                  # the new collection needs them all
            to_embed = chunks
            vectors = embed_texts([c.text for c in chunks])
        collection = client.create_collection(settings.collection, metadata={**DISTANCE, **pin})
        have = {}

    if to_embed:
        collection.upsert(ids=[c.id for c in to_embed], documents=[c.text for c in to_embed],
                          embeddings=vectors, metadatas=[c.metadata() for c in to_embed])
    embedded_ids = {c.id for c in to_embed}
    meta_only = [c for c in chunks if c.id in have and c.id not in embedded_ids
                 and have[c.id] != c.metadata()]
    if meta_only:
        collection.update(ids=[c.id for c in meta_only],
                          metadatas=[c.metadata() for c in meta_only])
    stale = sorted(set(have) - set(ids))
    if stale:
        collection.delete(ids=stale)
    return SyncResult(embedded=len(to_embed), metadata_updated=len(meta_only),
                      unchanged=len(chunks) - len(to_embed) - len(meta_only),
                      deleted=len(stale), total=int(collection.count()), rebuilt=rebuilt)


def _names(client: Any) -> set[str]:
    try:
        return {getattr(c, "name", c) for c in client.list_collections()}
    except Exception:
        return set()


def chunk_counts(settings: IndexerSettings, client: Any = None) -> dict[str, int]:
    """Chunks per doc_id in the collection: the proof that a deleted document left no
    orphans (RAGOps A2)."""
    client = client or get_client(settings)
    collection = _existing(client, settings)
    if collection is None:
        return {}
    counts: dict[str, int] = {}
    for meta in collection.get(include=["metadatas"])["metadatas"]:
        key = str(meta.get("doc_id") or meta.get("source"))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
