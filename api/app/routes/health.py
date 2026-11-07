"""Liveness and readiness (section 4.3). They answer different questions."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

router = APIRouter()
log = logging.getLogger("rahbar.health")


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request, response: Response) -> dict[str, object]:
    """Can this pod take traffic? 503 naming the dependency that failed, unless Chroma is
    reachable with a non-empty collection and Redis answers (section 4.3). The embedding
    pin check (section 4.4) joins these checks with Dev 2's guard."""
    state = request.app.state
    checks: dict[str, str] = {}
    try:
        n = state.retriever.count()
        checks["chroma"] = "ok" if n > 0 else "collection is empty"
    except Exception as exc:
        checks["chroma"] = f"unreachable or collection missing ({type(exc).__name__})"
    if state.cache.enabled:
        try:
            checks["redis"] = "ok" if state.cache.ping() else "no reply"
        except Exception as exc:
            checks["redis"] = f"unreachable ({type(exc).__name__})"
    failed = {k: v for k, v in checks.items() if v != "ok"}
    if failed:
        response.status_code = 503
        log.warning("not ready", extra={"failed": failed})
        return {"status": "not ready", "checks": checks}
    return {"status": "ready", "checks": checks}
