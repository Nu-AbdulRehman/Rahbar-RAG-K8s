"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

import httpx

from .config import IndexerSettings


def embed(texts: list[str], settings: IndexerSettings,
          client: httpx.Client | None = None) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else.

    POST {ollama_url}/api/embed with {"model": ..., "input": [texts]} returns
    {"embeddings": [[...], ...]}, in batches of settings.embed_batch_size. Any HTTP error,
    a missing vector or a vector of a different length raises, so the Job fails and
    Kubernetes retries it, instead of storing a partial index.
    """
    owned = client is None
    http = client or httpx.Client(timeout=settings.embed_timeout)
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), settings.embed_batch_size):
            batch = texts[start:start + settings.embed_batch_size]
            response = http.post(f"{settings.ollama_url.rstrip('/')}/api/embed",
                                 json={"model": settings.embed_model, "input": batch})
            response.raise_for_status()
            got = response.json().get("embeddings") or []
            if len(got) != len(batch):
                raise RuntimeError(f"{settings.embed_model} returned {len(got)} vectors "
                                   f"for {len(batch)} texts")
            vectors.extend(got)
    finally:
        if owned:
            http.close()
    if len({len(v) for v in vectors}) > 1:
        raise RuntimeError(f"{settings.embed_model} returned vectors of different lengths")
    return vectors
