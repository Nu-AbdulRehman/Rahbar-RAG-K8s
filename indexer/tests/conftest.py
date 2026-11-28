"""Every indexer test gets its own data lake. Without this, a test that runs the whole
pipeline on eval/fixtures would move the fixture files into the default lake under /tmp
(verification moves documents; it never deletes them)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_data_lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    lake = tmp_path / "datalake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake))
    return lake


def bag_of_words(texts: list[str], settings: object = None) -> list[list[float]]:
    """A deterministic stand-in for the embedding model: word counts hashed into 64 slots.
    Texts that share most words get a high cosine, as with a real model. No network."""
    import zlib

    vectors = []
    for text in texts:
        v = [0.0] * 64
        for word in text.lower().split():
            v[zlib.crc32(word.encode()) % 64] += 1.0
        vectors.append(v)
    return vectors


@pytest.fixture(autouse=True)
def no_embedding_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The uniqueness check embeds documents during a run; tests never call Ollama.
    (test_embed.py imported the real function before this patch, so it still tests it.)"""
    monkeypatch.setattr("pipeline.embed.embed", bag_of_words)
