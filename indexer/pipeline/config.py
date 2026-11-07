"""Indexer configuration, from the same ConfigMap the API reads (section 4.1).

The only module in the indexer that reads the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IndexerSettings:
    embed_model: str        # EMBED_MODEL: must equal the API's value (section 4.4)
    chroma_host: str
    chroma_port: int
    collection: str
    corpus_dir: str         # where the documents and _index.json sit inside the Job's pod
    chunk_size: int         # in words; see docs/PIPELINE.md, "Chunking"
    chunk_overlap: int      # in words
    ollama_url: str
    embed_batch_size: int = 32      # texts per POST /api/embed
    embed_timeout: float = 120.0    # seconds per embedding request
    ocr_dpi: int = 300              # render resolution for pages with no text layer
    redis_host: str = "redis"       # the last step bumps the cache generation (3.3)
    redis_port: int = 6379
    pod_name: str = "-"             # HOSTNAME: the Job's pod, for the start-up log line


def get_settings() -> IndexerSettings:
    return IndexerSettings(
        embed_model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        chroma_host=os.environ.get("CHROMA_HOST", "chroma"),
        chroma_port=int(os.environ.get("CHROMA_PORT", 8000)),
        collection=os.environ.get("CHROMA_COLLECTION", "rahbar"),
        corpus_dir=os.environ.get("CORPUS_DIR", "/corpus"),
        # 150/30 words: best recall@5 of six measured configs (docs/PIPELINE.md, "Chunking")
        chunk_size=int(os.environ.get("CHUNK_SIZE", 150)),
        chunk_overlap=int(os.environ.get("CHUNK_OVERLAP", 30)),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.minikube.internal:11434"),
        embed_batch_size=int(os.environ.get("EMBED_BATCH_SIZE", 32)),
        embed_timeout=float(os.environ.get("EMBED_TIMEOUT_SECONDS", 120)),
        ocr_dpi=int(os.environ.get("OCR_DPI", 300)),
        redis_host=os.environ.get("REDIS_HOST", "redis"),
        redis_port=int(os.environ.get("REDIS_PORT", 6379)),
        pod_name=os.environ.get("HOSTNAME", "-"),
    )
