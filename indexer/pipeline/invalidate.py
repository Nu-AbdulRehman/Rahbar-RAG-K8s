"""Last step of every index run: expire the semantic cache (section 3.3).

The API stores each cache entry with the generation number current when it was written,
and treats an entry from any other generation as a miss. Bumping the number expires the
whole cache in one atomic command, without scanning or deleting keys.
"""

from __future__ import annotations

from typing import Any

from .config import IndexerSettings

# Shared with api/app/providers/cache/: both sides must name the same key.
GENERATION_KEY = "rahbar:cache:generation"


def invalidate_cache(settings: IndexerSettings, client: Any = None) -> int:
    """Bump the cache generation and return the new value. Raises if Redis is down, so
    the Job fails and is retried: a new index behind an old cache answers nothing new."""
    if client is None:
        import redis

        client = redis.Redis(host=settings.redis_host, port=settings.redis_port,
                             socket_timeout=5, socket_connect_timeout=5)
    return int(client.incr(GENERATION_KEY))
