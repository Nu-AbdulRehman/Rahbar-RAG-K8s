"""Per-request stage timings for the trace record (RAGOps D1, D3).

A neutral module, like logjson.py, so the retriever can time its own embed and query
steps without importing services/. Each request starts a fresh dict; code outside a
request (tests, the startup pin check) times into nothing.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

stage_times: ContextVar[dict[str, float] | None] = ContextVar("stage_times", default=None)


def start() -> dict[str, float]:
    """Begin timing a request; returns the dict the stages write into (milliseconds)."""
    times: dict[str, float] = {}
    stage_times.set(times)
    return times


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Add the time spent inside the block to `name` (repeated stages add up, e.g. the
    generation retry)."""
    started = time.perf_counter()
    try:
        yield
    finally:
        times = stage_times.get()
        if times is not None:
            times[name] = round(times.get(name, 0.0) + (time.perf_counter() - started) * 1000, 1)
