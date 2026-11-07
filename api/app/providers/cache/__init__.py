from __future__ import annotations

from typing import Any

from ...config import Settings
from .semantic import NoCache, SemanticCache


def get_cache(settings: Settings, embedder: Any) -> SemanticCache | NoCache:
    """CACHE=redis in the ConfigMap; `none` (the default) keeps `make dev` free of Redis."""
    if settings.cache == "none":
        return NoCache()
    if settings.cache == "redis":
        import redis

        client = redis.Redis(host=settings.redis_host, port=settings.redis_port,
                             socket_timeout=settings.redis_timeout,
                             socket_connect_timeout=settings.redis_timeout)
        return SemanticCache(client, embedder, settings.cache_threshold,
                             settings.cache_max_entries)
    raise ValueError(f"unknown CACHE {settings.cache!r}; expected redis or none")
