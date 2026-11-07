"""Semantic cache and readiness (§3.3, §4.3). A fake Redis and a fake embedder: no network."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.providers.cache import get_cache
from app.providers.cache.semantic import GENERATION_KEY, SemanticCache
from app.providers.llm.base import Completion, Prompt
from app.schemas import Passage, Turn
from app.services.answer import answer_question

FEES = Passage(chunk_id="fee#6", source="fee.html", section="Fee Refund Policy", page=1,
               score=0.8, text="Upto 15th day: 80% refund.")


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise ConnectionError("redis down")

    def get(self, key: str) -> Any:
        self._check()
        return self.data.get(key)

    def incr(self, key: str) -> int:
        self.data[key] = int(self.data.get(key) or 0) + 1
        return self.data[key]

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        self._check()
        return list(self.data.get(key, []))

    def ping(self) -> bool:
        self._check()
        return True

    def pipeline(self) -> FakeRedis:
        self._check()
        return self

    def rpush(self, key: str, value: str) -> None:
        self.data.setdefault(key, []).append(value)

    def ltrim(self, key: str, start: int, end: int) -> None:
        self.data[key] = self.data[key][start:] if start < 0 else self.data[key]

    def expire(self, key: str, seconds: int) -> None:
        pass

    def execute(self) -> None:
        pass


class Embedder:
    """Near-identical wordings share a direction; anything else is orthogonal."""

    VECTORS = {"How much is refunded in 15 days?": [1.0, 0.0, 0.0],
               "How much refund do I get within 15 days?": [0.98, 0.2, 0.0],
               "What is the refund for MS students?": [0.8, 0.6, 0.0],
               # a follow-up that WOULD hit, so skipping the lookup is what keeps it a miss
               "What about that within 15 days?": [0.99, 0.1, 0.0]}

    def embed(self, text: str) -> list[float]:
        return self.VECTORS.get(text, [0.0, 0.0, 1.0])


class Provider:
    name = "counting"

    def __init__(self, reply: dict | None = None) -> None:
        self.calls = 0
        self.reply = reply

    def complete(self, prompt: Prompt) -> Completion:
        self.calls += 1
        reply = self.reply or {
            "reasoning": "r", "answer": "80% within 15 days.", "answered_from_context": True,
            "confidence": "high",
            "citations": [{"source": "fee.html", "section": "Fee Refund Policy", "page": 1}]}
        return Completion(json.dumps(reply))


class Retriever:
    name = "fixed"

    def __init__(self, score: float = 0.8) -> None:
        self.score = score

    def count(self) -> int:
        return 1

    def retrieve(self, question: str, k: int, include_superseded: bool = False) -> list[Passage]:
        return [FEES.model_copy(update={"score": self.score})]


def _setup(threshold: float = 0.95) -> tuple[SemanticCache, FakeRedis]:
    redis = FakeRedis()
    return SemanticCache(redis, Embedder(), threshold, max_entries=50), redis


def _ask(cache: SemanticCache, question: str, provider: Provider | None = None,
         retriever: Retriever | None = None, history: list[Turn] | None = None) -> Any:
    return answer_question(question, retriever or Retriever(), provider or Provider(),
                           Settings(relevance_floor=0.5), history=history, cache=cache)


def test_a_similar_question_is_a_hit_without_calling_the_model() -> None:
    cache, _ = _setup()
    provider = Provider()
    first = _ask(cache, "How much is refunded in 15 days?", provider)
    second = _ask(cache, "How much refund do I get within 15 days?", provider)   # cos 0.98
    assert provider.calls == 1
    assert first.cached is False and second.cached is True
    assert second.answer == first.answer and second.citations == first.citations


def test_the_threshold_comes_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CACHE_THRESHOLD", "0.99")
    from app.config import get_settings

    settings = get_settings()
    assert settings.cache_threshold == 0.99
    cache, _ = _setup(settings.cache_threshold)
    provider = Provider()
    _ask(cache, "How much is refunded in 15 days?", provider)
    assert _ask(cache, "How much refund do I get within 15 days?", provider).cached is False
    assert provider.calls == 2                                # 0.98 is below 0.99


def test_abstentions_are_not_cached() -> None:
    cache, redis = _setup()
    _ask(cache, "How much is refunded in 15 days?", retriever=Retriever(score=0.1))
    assert not any(k.startswith("rahbar:cache:entries") for k in redis.data)


@pytest.mark.parametrize("reply", [
    {"reasoning": "r", "answer": "Not covered.", "answered_from_context": False,
     "confidence": "low", "citations": []},                                  # out of scope
    {"bad": "json"},                                                         # failed: fallback
])
def test_out_of_scope_and_failed_answers_are_not_cached(reply: dict) -> None:
    cache, redis = _setup()
    _ask(cache, "How much is refunded in 15 days?", Provider(reply))
    assert redis.data.get("rahbar:cache:entries:0") is None


def test_follow_ups_skip_the_cache_both_ways() -> None:
    cache, redis = _setup()
    history = [Turn(question="Do I get my fee back?", answer="No.")]
    provider = Provider()
    _ask(cache, "How much is refunded in 15 days?", provider)               # cached
    follow = _ask(cache, "What about that within 15 days?", provider, history=history)
    assert follow.cached is False and provider.calls == 2                   # no lookup
    assert len(redis.data["rahbar:cache:entries:0"]) == 1                   # no store


def test_an_index_run_invalidates_the_cache() -> None:
    cache, redis = _setup()
    provider = Provider()
    _ask(cache, "How much is refunded in 15 days?", provider)
    redis.incr(GENERATION_KEY)          # what indexer/pipeline/invalidate.py does
    assert _ask(cache, "How much is refunded in 15 days?", provider).cached is False
    assert provider.calls == 2


def test_redis_down_is_a_miss_not_a_500() -> None:
    cache, redis = _setup()
    redis.down = True
    response = _ask(cache, "How much is refunded in 15 days?")
    assert response.answered_from_context is True and response.cached is False


def test_unknown_cache_setting_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown CACHE"):
        get_cache(Settings(cache="memcached"), Embedder())


# --- readiness ------------------------------------------------------------------------

@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_ready_with_a_non_empty_index(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["checks"]["chroma"] == "ok"


def test_not_ready_names_an_empty_collection_and_a_dead_redis(client: TestClient) -> None:
    class Empty(Retriever):
        def count(self) -> int:
            return 0

    cache, redis = _setup()
    redis.down = True
    client.app.state.retriever, client.app.state.cache = Empty(), cache  # type: ignore[attr-defined]
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["chroma"] == "collection is empty"
    assert r.json()["checks"]["redis"].startswith("unreachable")


def test_liveness_ignores_every_dependency(client: TestClient) -> None:
    class Broken(Retriever):
        def count(self) -> int:
            raise ConnectionError("chroma down")

    client.app.state.retriever = Broken()  # type: ignore[attr-defined]
    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz").status_code == 200
