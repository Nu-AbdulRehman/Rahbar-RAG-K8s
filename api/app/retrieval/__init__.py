from __future__ import annotations

from typing import Any

from ..config import Settings
from .base import Retriever


def get_retriever(settings: Settings, embedder: Any = None) -> Retriever:
    if settings.retriever == "stub":
        from .stub import StubRetriever

        return StubRetriever()
    if settings.retriever == "chroma":
        from ..providers.llm.embed import OllamaEmbedder
        from .chroma import ChromaRetriever

        return ChromaRetriever(settings, embedder or OllamaEmbedder(settings))
    raise ValueError(f"unknown RETRIEVER {settings.retriever!r}; expected stub or chroma")
