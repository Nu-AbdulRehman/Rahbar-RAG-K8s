"""Stage 5: Store. The only code in the whole system that writes to Chroma.

Re-indexing upserts into the live collection and then deletes the chunks that no longer
exist, so the API keeps serving the old index until the new one is complete, with no
empty-collection window (DECISIONS.md D15). The collection is rebuilt from scratch only
when its pinned embedding metadata changes, because vectors from two models (or two
dimensions) cannot share a collection.
"""

from __future__ import annotations

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
