"""Semantic cache on Redis (section 3.3, ADR 0003).

A hit is a stored question whose embedding has cosine similarity at or above
CACHE_THRESHOLD with the new one. Entries live in one Redis list per cache generation;
the indexer bumps the generation as the last step of every run (indexer/pipeline/
invalidate.py), so a re-index expires every entry at once without deleting anything.

Every Redis error degrades to a miss: the cache can make answers faster, never fail them.
"""

from __future__ import annotations

import base64
import json
import logging
import math
from array import array
from typing import Any, Protocol

log = logging.getLogger("rahbar.cache")

GENERATION_KEY = "rahbar:cache:generation"     # the same key the indexer increments
ENTRIES_KEY = "rahbar:cache:entries:{generation}"
ENTRY_TTL_SECONDS = 7 * 24 * 3600              # old generations clean themselves up


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


def _pack(vector: list[float]) -> str:
    return base64.b64encode(array("f", vector).tobytes()).decode()


def _unpack(data: str) -> array:
    out = array("f")
    out.frombytes(base64.b64decode(data))
    return out


def cosine(a: Any, b: Any) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class SemanticCache:
    enabled = True

    def __init__(self, client: Any, embedder: Embedder, threshold: float,
                 max_entries: int) -> None:
        self.client = client
        self.embedder = embedder
        self.threshold = threshold
        self.max_entries = max_entries

    def _key(self) -> str:
        return ENTRIES_KEY.format(generation=int(self.client.get(GENERATION_KEY) or 0))

    def lookup(self, question: str) -> tuple[dict | None, float]:
        """(the cached answer payload or None, best similarity seen). Errors are a miss."""
        try:
            vector = self.embedder.embed(question)
            best, payload = 0.0, None
            # ponytail: linear scan of at most CACHE_MAX_ENTRIES vectors per lookup;
            # move to a Redis vector index (redis-stack) if the cache must hold more.
            for raw in self.client.lrange(self._key(), 0, -1):
                entry = json.loads(raw)
                score = cosine(vector, _unpack(entry["v"]))
                if score > best:
                    best, payload = score, entry["r"]
            return (payload if best >= self.threshold else None), round(best, 4)
        except Exception as exc:
            log.warning("cache lookup failed", extra={"error": type(exc).__name__})
            return None, 0.0

    def store(self, question: str, payload: dict) -> bool:
        try:
            entry = json.dumps({"v": _pack(self.embedder.embed(question)), "r": payload})
            key = self._key()
            pipe = self.client.pipeline()
            pipe.rpush(key, entry)
            pipe.ltrim(key, -self.max_entries, -1)       # keep the newest entries
            pipe.expire(key, ENTRY_TTL_SECONDS)
            pipe.execute()
            return True
        except Exception as exc:
            log.warning("cache store failed", extra={"error": type(exc).__name__})
            return False

    def ping(self) -> bool:
        return bool(self.client.ping())


class NoCache:
    """CACHE=none: every lookup misses and nothing is stored (make dev, unit tests)."""

    enabled = False

    def lookup(self, question: str) -> tuple[dict | None, float]:
        return None, 0.0

    def store(self, question: str, payload: dict) -> bool:
        return False

    def ping(self) -> bool:
        return True
