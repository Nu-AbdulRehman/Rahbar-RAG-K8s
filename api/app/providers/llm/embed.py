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
        # Length of the vectors this model returns, known after the first call. The
        # embedding-pin check compares it with the index (services/pin.py).
        self.dimension: int | None = None
        # The model's Ollama digest, its "version" in the trace record (RAGOps D1): the
        # name alone does not change when a model is re-pulled. Looked up once.
        self.digest: str | None = None
        self.tags_url = f"{settings.ollama_url.rstrip('/')}/api/tags"

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
        self.dimension = len(vector)
        return list(vector)

    def lookup_digest(self) -> str | None:
        """GET /api/tags once and keep this model's digest (first 12 hex characters, as
        `ollama list` prints it). A failure leaves it None and is retried next time."""
        if self.digest is None:
            response = self.client.get(self.tags_url)
            response.raise_for_status()
            names = {self.model, f"{self.model}:latest"}
            for m in response.json().get("models") or []:
                if m.get("name") in names or m.get("model") in names:
                    self.digest = str(m.get("digest", ""))[:12] or None
                    break
        return self.digest
