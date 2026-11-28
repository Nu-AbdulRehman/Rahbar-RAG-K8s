"""RAGOps A2 against an in-memory Chroma: re-running on an unchanged corpus embeds nothing,
a changed document replaces only its own chunks, a deleted one leaves no orphans."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from pipeline.config import get_settings
from pipeline.models import Chunk
from pipeline.store import chunk_counts, sync


class Collection:
    def __init__(self, name: str, metadata: dict[str, Any]) -> None:
        self.name, self.metadata = name, metadata
        self.rows: dict[str, tuple[str, list[float], dict[str, Any]]] = {}

    def get(self, include: list[str]) -> dict[str, list[Any]]:
        return {"ids": list(self.rows), "metadatas": [m for _, _, m in self.rows.values()]}

    def upsert(self, ids, documents, embeddings, metadatas) -> None:  # type: ignore[no-untyped-def]
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, e, m)

    def update(self, ids, metadatas) -> None:  # type: ignore[no-untyped-def]
        for i, m in zip(ids, metadatas):
            d, e, _ = self.rows[i]
            self.rows[i] = (d, e, m)

    def delete(self, ids: list[str]) -> None:
        for i in ids:
            del self.rows[i]

    def count(self) -> int:
        return len(self.rows)


class Client:
    def __init__(self) -> None:
        self.collections: dict[str, Collection] = {}

    def get_collection(self, name: str) -> Collection:
        return self.collections[name]

    def create_collection(self, name: str, metadata: dict[str, Any]) -> Collection:
        self.collections[name] = Collection(name, metadata)
        return self.collections[name]

    def delete_collection(self, name: str) -> None:
        del self.collections[name]

    def list_collections(self) -> list[Collection]:
        return list(self.collections.values())


class Embedder:
    def __init__(self, dim: int = 2) -> None:
        self.calls, self.dim = 0, dim

    def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls += len(texts)
        return [[1.0] * self.dim for _ in texts]


def _doc(doc_id: str, texts: list[str], superseded: bool = False) -> list[Chunk]:
    return [Chunk(f"{doc_id}.md#{i:04d}", t, f"{doc_id}.md", "1. S", 1, "2026", superseded,
                  doc_id) for i, t in enumerate(texts)]


@pytest.fixture()
def corpus() -> list[Chunk]:
    return _doc("rules", ["attendance", "warning", "repeat"]) + _doc("fees", ["tuition", "refund"])


def test_an_unchanged_corpus_embeds_zero_chunks(corpus: list[Chunk]) -> None:
    client, embed = Client(), Embedder()
    first = sync(corpus, get_settings(), embed, client)
    assert (first.embedded, first.total) == (5, 5)
    again = sync(corpus, get_settings(), embed, client)
    assert (again.embedded, again.metadata_updated, again.unchanged, again.deleted) == (0, 0, 5, 0)
    assert embed.calls == 5                                  # nothing embedded the second time


def test_a_changed_document_replaces_only_its_own_chunks(corpus: list[Chunk]) -> None:
    client, embed = Client(), Embedder()
    sync(corpus, get_settings(), embed, client)
    changed = _doc("rules", ["attendance", "warning REVISED"]) + _doc("fees", ["tuition", "refund"])
    result = sync(changed, get_settings(), embed, client)
    assert (result.embedded, result.deleted, result.unchanged) == (1, 1, 3)
    assert chunk_counts(get_settings(), client) == {"fees": 2, "rules": 2}


def test_a_deleted_document_leaves_no_orphan_chunks(corpus: list[Chunk]) -> None:
    client = Client()
    sync(corpus, get_settings(), Embedder(), client)
    result = sync(_doc("fees", ["tuition", "refund"]), get_settings(), Embedder(), client)
    assert result.deleted == 3
    assert chunk_counts(get_settings(), client) == {"fees": 2}


def test_a_superseded_flag_is_updated_without_re_embedding(corpus: list[Chunk]) -> None:
    client, embed = Client(), Embedder()
    sync(corpus, get_settings(), embed, client)
    archived = [replace(c, superseded=True) if c.doc_id == "rules" else c for c in corpus]
    result = sync(archived, get_settings(), embed, client)
    assert (result.embedded, result.metadata_updated) == (0, 3)
    rows = client.collections["rahbar"].rows
    assert all(m["superseded"] for _, _, m in rows.values() if m["doc_id"] == "rules")


def test_a_new_embedding_model_rebuilds_with_every_chunk(
        corpus: list[Chunk], monkeypatch: pytest.MonkeyPatch) -> None:
    client = Client()
    sync(corpus, get_settings(), Embedder(), client)
    monkeypatch.setenv("EMBED_MODEL", "all-minilm")
    embed = Embedder(dim=3)
    result = sync(corpus, get_settings(), embed, client)
    assert result.rebuilt and result.embedded == 5 and embed.calls == 5
    assert client.collections["rahbar"].metadata["embed_model"] == "all-minilm"
    assert client.collections["rahbar"].metadata["dimension"] == 3
