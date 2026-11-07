"""Question embedding with the pinned model, through the same Ollama the indexer uses
(section 3.2 step 3). The wire format matches indexer/pipeline/embed.py."""

from __future__ import annotations

import httpx

from ...config import Settings


class OllamaEmbedder:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.model = settings.embed_model
        self.url = f"{settings.ollama_url.rstrip('/')}/api/embed"
        self.client = client or httpx.Client(timeout=settings.embed_timeout)
        # One-entry memo: the cache lookup and the retriever embed the same question
        # back to back, and the second call should not cost a round trip.
        self._last: tuple[str, list[float]] | None = None

    def embed(self, text: str) -> list[float]:
        last = self._last
        if last is not None and last[0] == text:
            return list(last[1])
        response = self.client.post(self.url, json={"model": self.model, "input": [text]})
        response.raise_for_status()
        vectors = response.json().get("embeddings") or []
        if len(vectors) != 1:
            raise RuntimeError(f"{self.model} returned {len(vectors)} vectors for 1 text")
        vector = [float(v) for v in vectors[0]]
        self._last = (text, vector)
        return list(vector)
