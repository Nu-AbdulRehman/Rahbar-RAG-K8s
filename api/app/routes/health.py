"""Liveness and readiness (section 4.3). They answer different questions."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from ..services.pin import pin_conflict, report

router = APIRouter()
log = logging.getLogger("rahbar.health")


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request, response: Response) -> dict[str, object]:
    """Can this pod take traffic? 503 naming the dependency that failed, unless Chroma is
    reachable with a non-empty collection, the collection's embedding pin matches this
    api's EMBED_MODEL and vector dimension (section 4.4), and Redis answers (4.3)."""
    state = request.app.state
    checks: dict[str, str] = {}
    try:
        n = state.retriever.count()
        checks["chroma"] = "ok" if n > 0 else "collection is empty"
        pin = getattr(state.retriever, "pin", lambda: None)()
        embedder = getattr(state, "embedder", None)
        conflict = pin_conflict(pin, state.settings, getattr(embedder, "dimension", None))
        state.pin_conflict = report(conflict, getattr(state, "pin_conflict", None))
        if pin is not None:
            checks["embedding_pin"] = conflict or "ok"
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
