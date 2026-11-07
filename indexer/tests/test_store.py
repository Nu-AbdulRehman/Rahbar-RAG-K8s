"""Stage 5 against an in-memory fake of the Chroma client (§3.1, §4.4)."""

from __future__ import annotations

from typing import Any

import pytest

from pipeline.config import get_settings
from pipeline.models import Chunk
from pipeline.store import store


class FakeCollection:
    def __init__(self, metadata: dict[str, Any]) -> None:
        self.metadata = metadata
        self.rows: dict[str, tuple] = {}

    def upsert(self, ids, documents, embeddings, metadatas) -> None:  # type: ignore[no-untyped-def]
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, e, m)

    def get(self, include: list[str]) -> dict[str, list[str]]:
        return {"ids": list(self.rows)}

    def delete(self, ids: list[str]) -> None:
        for i in ids:
            del self.rows[i]

    def count(self) -> int:
        return len(self.rows)


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}
        self.rebuilds = 0

    def get_or_create_collection(self, name: str, metadata: dict[str, Any]) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection(metadata))

    def create_collection(self, name: str, metadata: dict[str, Any]) -> FakeCollection:
        self.collections[name] = FakeCollection(metadata)
        return self.collections[name]

    def delete_collection(self, name: str) -> None:
        self.rebuilds += 1
        del self.collections[name]


def _chunks(n: int, prefix: str = "doc.md") -> list[Chunk]:
    return [Chunk(f"{prefix}#{i:04d}", f"text {i}", prefix, "1. Section", 1, "2026", False)
            for i in range(n)]


def test_store_writes_rows_metadata_and_the_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_MODEL", "pinned-model")
    client = FakeClient()
    assert store(_chunks(3), [[0.1, 0.2]] * 3, get_settings(), client) == 3
    col = client.collections["rahbar"]
    assert col.metadata == {"hnsw:space": "cosine", "embed_model": "pinned-model",
                            "dimension": 2}
    _, vector, meta = col.rows["doc.md#0000"]
    assert vector == [0.1, 0.2]
    assert set(meta) == {"source", "section", "page", "doc_version", "superseded"}


def test_reindex_upserts_and_prunes_without_a_rebuild() -> None:
    client = FakeClient()
    store(_chunks(5), [[1.0]] * 5, get_settings(), client)
    assert store(_chunks(3), [[1.0]] * 3, get_settings(), client) == 3   # 2 chunks gone
    assert store(_chunks(3), [[1.0]] * 3, get_settings(), client) == 3   # safe to repeat
    assert client.rebuilds == 0


def test_a_new_model_or_dimension_rebuilds_the_collection(
        monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.collections["rahbar"] = FakeCollection(
        {"hnsw:space": "cosine", "embed_model": "dummy-768", "dimension": 768})
    client.collections["rahbar"].rows["dummy-001"] = ("x", [0.0] * 768, {})
    assert store(_chunks(2), [[1.0, 0.0]] * 2, get_settings(), client) == 2
    assert client.rebuilds == 1
    assert "dummy-001" not in client.collections["rahbar"].rows


@pytest.mark.parametrize("chunks, vectors", [([], []), (_chunks(2), [[1.0]])])
def test_refuses_an_empty_or_mismatched_write(chunks: list, vectors: list) -> None:
    client = FakeClient()
    with pytest.raises(ValueError):
        store(chunks, vectors, get_settings(), client)
    assert client.collections == {}
