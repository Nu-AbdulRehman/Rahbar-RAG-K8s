"""The real retriever (sections 3.2 and 4.4). Read only: it never creates, adds to or
deletes from a collection; the indexer Job is the only writer."""

from __future__ import annotations

from typing import Any, Protocol

from ..config import Settings
from ..schemas import Passage


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class ChromaRetriever:
    name = "chroma"

    def __init__(self, settings: Settings, embedder: Embedder, client: Any = None) -> None:
        self.settings = settings
        self.embedder = embedder
        if client is None:
            import chromadb  # the thin client, from chromadb-client in requirements.txt
            from chromadb.config import Settings as ChromaSettings

            client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                                         settings=ChromaSettings(anonymized_telemetry=False))
        self.client = client

    def collection(self) -> Any:
        """Look the collection up on every call: after a model change the indexer rebuilds
        it under the same name, and a cached handle would point at the deleted one."""
        return self.client.get_collection(self.settings.collection)

    def count(self) -> int:
        return int(self.collection().count())

    def retrieve(self, question: str, k: int, include_superseded: bool = False) -> list[Passage]:
        vector = self.embedder.embed(question)          # the pinned EMBED_MODEL
        where = None if include_superseded else {"superseded": False}
        result = self.collection().query(query_embeddings=[vector], n_results=k, where=where,
                                         include=["documents", "metadatas", "distances"])
        passages = []
        for chunk_id, text, meta, distance in zip(result["ids"][0], result["documents"][0],
                                                   result["metadatas"][0],
                                                   result["distances"][0]):
            page = meta.get("page")
            passages.append(Passage(
                chunk_id=chunk_id, text=text or "", source=str(meta.get("source", "")),
                section=str(meta.get("section", "")),
                page=int(page) if page is not None else None,
                score=round(1.0 - float(distance), 4),   # cosine distance to similarity
            ))
        return passages
