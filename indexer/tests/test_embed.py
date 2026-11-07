"""Stage 4 against a fake Ollama: no network, no model (§3.1)."""

from __future__ import annotations

import json

import httpx
import pytest

from pipeline.config import get_settings
from pipeline.embed import embed


def _client(calls: list[dict], dim: int = 4, drop: bool = False) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        vectors = [[float(len(t))] * dim for t in body["input"]]
        return httpx.Response(200, json={"embeddings": vectors[:-1] if drop else vectors})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_batches_use_the_pinned_model_and_keep_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_MODEL", "pinned-model")
    monkeypatch.setenv("EMBED_BATCH_SIZE", "2")
    calls: list[dict] = []
    vectors = embed(["a", "bb", "ccc"], get_settings(), _client(calls))
    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0]
    assert [c["model"] for c in calls] == ["pinned-model", "pinned-model"]
    assert [len(c["input"]) for c in calls] == [2, 1]


def test_a_missing_vector_fails_the_run() -> None:
    with pytest.raises(RuntimeError, match="returned 1 vectors for 2 texts"):
        embed(["a", "b"], get_settings(), _client([], drop=True))


def test_an_http_error_fails_the_run() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(httpx.HTTPStatusError):
        embed(["a"], get_settings(), client)
