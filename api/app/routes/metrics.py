"""Prometheus metrics at /metrics (section 4.8).

Labels are bounded: route templates and fixed outcome names, never question text.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

router = APIRouter()

REQUESTS = Counter("rahbar_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "rahbar_request_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
FOLLOWUPS = Counter("rahbar_followups_total", "Questions treated as follow-ups (ADR 0002)")
CACHE_LOOKUPS = Counter("rahbar_cache_lookups_total", "Semantic cache lookups by result",
                        ["result"])          # hit | miss | skipped (follow-up)
CACHE_STORES = Counter("rahbar_cache_stores_total", "Answers written to the semantic cache")
SUMMARY_FAILURES = Counter("rahbar_summary_failures_total",
                           "Conversation summary calls that failed; the old summary was kept")


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
