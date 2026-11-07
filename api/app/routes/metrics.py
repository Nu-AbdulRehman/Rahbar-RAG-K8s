"""Prometheus metrics at /metrics (section 4.8).

Labels are bounded: route templates and fixed outcome names, never question text.
Hit ratio across pods in PromQL:
  sum(rate(rahbar_cache_lookups_total{result="hit"}[5m]))
    / sum(rate(rahbar_cache_lookups_total{result=~"hit|miss"}[5m]))
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

router = APIRouter()

REQUESTS = Counter("rahbar_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "rahbar_request_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
STAGE_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60)
RETRIEVAL_LATENCY = Histogram("rahbar_retrieval_seconds",
                              "Embedding the question and querying Chroma", buckets=STAGE_BUCKETS)
GENERATION_LATENCY = Histogram("rahbar_generation_seconds",
                               "LLM generation, including the one retry", buckets=STAGE_BUCKETS)
TOKENS = Histogram("rahbar_tokens_per_request", "LLM tokens per answered request",
                   ["direction"], buckets=(50, 100, 250, 500, 1000, 2000, 4000, 8000))
ABSTENTIONS = Counter("rahbar_abstentions_total",
                      "Questions declined because nothing cleared the relevance floor")
FALLBACKS = Counter("rahbar_fallbacks_total", "Canned answers returned", ["reason"])
CACHE_HIT_RATIO = Gauge("rahbar_cache_hit_ratio",
                        "Hits / (hits + misses) in this pod since it started")
FOLLOWUPS = Counter("rahbar_followups_total", "Questions treated as follow-ups (ADR 0002)")
CACHE_LOOKUPS = Counter("rahbar_cache_lookups_total", "Semantic cache lookups by result",
                        ["result"])          # hit | miss | skipped (follow-up)
CACHE_STORES = Counter("rahbar_cache_stores_total", "Answers written to the semantic cache")
SUMMARY_FAILURES = Counter("rahbar_summary_failures_total",
                           "Conversation summary calls that failed; the old summary was kept")


_cache_seen = {"hit": 0, "miss": 0}


def record_cache_lookup(result: str) -> None:
    """result: hit | miss | skipped. Skipped lookups (follow-ups, cache off) do not count
    towards the ratio."""
    CACHE_LOOKUPS.labels(result=result).inc()
    if result in _cache_seen:
        _cache_seen[result] += 1
        CACHE_HIT_RATIO.set(_cache_seen["hit"] / (_cache_seen["hit"] + _cache_seen["miss"]))


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
