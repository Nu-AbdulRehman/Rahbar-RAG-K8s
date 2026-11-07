"""The embedding pin (section 4.4): a mismatch keeps the pod not ready and names both
values; a match changes nothing. Stubs only."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services.pin import pin_conflict


class PinnedRetriever:
    name = "pinned"

    def __init__(self, pin: dict[str, Any]) -> None:
        self._pin = pin

    def retrieve(self, question: str, k: int, include_superseded: bool = False) -> list[Any]:
        return []

    def count(self) -> int:
        return 3

    def pin(self) -> dict[str, Any]:
        return self._pin


class FakeEmbedder:
    def __init__(self, dimension: int | None) -> None:
        self.dimension = dimension


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    from app.main import app

    with TestClient(app) as c:
        yield c


def _use(client: TestClient, pin: dict[str, Any], dimension: int | None = 768) -> None:
    state = client.app.state  # type: ignore[attr-defined]
    state.retriever, state.embedder = PinnedRetriever(pin), FakeEmbedder(dimension)


def test_a_model_mismatch_is_not_ready_and_names_both_models(
        client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    """The section 4.4 demonstration: the index says dummy-768, the ConfigMap says
    nomic-embed-text."""
    _use(client, {"embed_model": "dummy-768", "dimension": 768})
    with caplog.at_level(logging.ERROR, logger="rahbar.pin"):
        r = client.get("/readyz")
    assert r.status_code == 503
    pin = r.json()["checks"]["embedding_pin"]
    assert "'dummy-768'" in pin and "'nomic-embed-text'" in pin
    lines = [rec for rec in caplog.records if rec.getMessage() == "embedding pin mismatch"]
    assert len(lines) == 1
    assert "dummy-768" in lines[0].conflict and "nomic-embed-text" in lines[0].conflict  # type: ignore[attr-defined]


def test_the_conflict_is_logged_once_not_on_every_probe(
        client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    _use(client, {"embed_model": "dummy-768", "dimension": 768})
    with caplog.at_level(logging.ERROR, logger="rahbar.pin"):
        for _ in range(3):
            assert client.get("/readyz").status_code == 503
    assert sum(rec.getMessage() == "embedding pin mismatch" for rec in caplog.records) == 1


def test_a_dimension_mismatch_is_not_ready_even_when_the_names_agree(client: TestClient) -> None:
    _use(client, {"embed_model": "nomic-embed-text", "dimension": 384}, dimension=768)
    r = client.get("/readyz")
    assert r.status_code == 503
    assert "384" in r.json()["checks"]["embedding_pin"]
    assert "768" in r.json()["checks"]["embedding_pin"]


def test_a_matching_pin_is_ready(client: TestClient) -> None:
    _use(client, {"embed_model": "nomic-embed-text", "dimension": 768})
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["checks"]["embedding_pin"] == "ok"


def test_a_re_index_with_the_right_model_clears_the_conflict(client: TestClient) -> None:
    _use(client, {"embed_model": "dummy-768", "dimension": 768})
    assert client.get("/readyz").status_code == 503
    _use(client, {"embed_model": "nomic-embed-text", "dimension": 768})
    assert client.get("/readyz").status_code == 200


@pytest.mark.parametrize("pin, dimension, bad", [
    ({"embed_model": "nomic-embed-text", "dimension": 768}, 768, False),
    ({"embed_model": "nomic-embed-text", "dimension": 768}, None, False),  # not embedded yet
    ({"embed_model": "all-minilm", "dimension": 384}, 768, True),
    ({"dimension": 768}, 768, True),                                      # no model recorded
    ({"embed_model": "nomic-embed-text"}, 768, True),                     # no dimension recorded
    (None, 768, False),                                                   # stub: no index
])
def test_pin_conflict(pin: dict[str, Any] | None, dimension: int | None, bad: bool) -> None:
    assert (pin_conflict(pin, Settings(embed_model="nomic-embed-text"), dimension) is not None) is bad
