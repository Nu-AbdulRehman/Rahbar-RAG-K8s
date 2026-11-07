"""The whole run on the fixture corpus with fakes for Ollama, Chroma and Redis (§3.1, §3.3):
every stage runs, and the cache is invalidated last."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipeline import run

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def test_full_run_stores_fixture_chunks_then_invalidates_the_cache(
        monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    stored: dict[str, Any] = {}

    def fake_embed(texts: list[str], settings: Any) -> list[list[float]]:
        events.append("embed")
        return [[1.0, 0.0]] * len(texts)

    def fake_store(chunks: list, vectors: list, settings: Any) -> int:
        events.append("store")
        stored["chunks"] = chunks
        return len(chunks)

    def fake_invalidate(settings: Any) -> int:
        events.append("invalidate")
        return 7

    monkeypatch.setenv("CORPUS_DIR", str(FIXTURES))
    monkeypatch.setattr("pipeline.embed.embed", fake_embed)
    monkeypatch.setattr("pipeline.store.store", fake_store)
    monkeypatch.setattr(run, "invalidate_cache", fake_invalidate)
    monkeypatch.setattr("sys.argv", ["pipeline.run"])

    assert run.main() == 0
    assert events == ["embed", "store", "invalidate"]
    sources = {c.source for c in stored["chunks"]}
    assert sources == {"academic-rules-2023.md", "academic-rules-2026.md", "fees-2026.md"}


def test_a_redis_failure_fails_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(settings: Any) -> int:
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr("pipeline.dummy.write_dummy_index", lambda s, c: 3)
    monkeypatch.setattr("pipeline.store.get_client", lambda s: None)
    monkeypatch.setattr(run, "invalidate_cache", down)
    monkeypatch.setattr("sys.argv", ["pipeline.run", "--dummy"])
    with pytest.raises(ConnectionError):
        run.main()


def test_invalidate_bumps_the_shared_generation_key() -> None:
    from pipeline.config import get_settings
    from pipeline.invalidate import GENERATION_KEY, invalidate_cache

    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, int] = {}

        def incr(self, key: str) -> int:
            self.values[key] = self.values.get(key, 0) + 1
            return self.values[key]

    fake = FakeRedis()
    assert invalidate_cache(get_settings(), fake) == 1
    assert invalidate_cache(get_settings(), fake) == 2
    assert GENERATION_KEY == "rahbar:cache:generation"
