"""The API process. It reads the index; it never builds it (section 4.2).

Run locally with stubs:   make dev     (then open http://localhost:8000)
Run in the container:     uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .logjson import configure_logging, request_id_var
from .providers.cache import get_cache
from .providers.llm import get_provider
from .providers.llm.embed import OllamaEmbedder
from .retrieval import get_retriever
from .routes import ask, health, metrics
from .services.pin import pin_conflict
from .services.pin import report as pin_report

log = logging.getLogger("rahbar.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    # One embedder for the retriever and the cache, so a question is embedded once.
    embedder = OllamaEmbedder(settings)
    app.state.retriever = get_retriever(settings, embedder)
    app.state.provider = get_provider(settings)
    app.state.cache = get_cache(settings, embedder)
    app.state.embedder = embedder
    app.state.pin_conflict = None
    # The embedding pin (section 4.4), checked once here and again on every /readyz, since
    # a re-index can change it while the pod runs. This process only reads the index.
    # In a thread: on a fresh cluster the Chroma Service has no endpoints yet and the
    # connect hangs past the 60 s startup probe, which would kill the pod before it
    # serves /healthz (docs/failure-log.md). /readyz stays 503 until the check passes.
    threading.Thread(target=_check_pin_at_startup, args=(app,), daemon=True,
                     name="pin-check").start()
    log.info(
        "api started",
        extra={"retriever": settings.retriever, "llm_provider": settings.llm_provider,
               "embed_model": settings.embed_model, "top_k": settings.top_k,
               "cache": settings.cache},
    )
    yield


def _check_pin_at_startup(app: FastAPI) -> None:
    state = app.state
    try:
        pin = getattr(state.retriever, "pin", lambda: None)()
        if pin is not None and pin.get("embed_model") == state.settings.embed_model:
            state.embedder.embed("embedding pin probe")      # learn this model's dimension
    except Exception as exc:  # Chroma or Ollama still booting: /readyz checks again
        log.warning("embedding pin not checked at startup", extra={"error": type(exc).__name__})
        return
    state.pin_conflict = pin_report(pin_conflict(pin, state.settings, state.embedder.dimension),
                                    None)


app = FastAPI(title="RAHBAR API", lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_var.set(rid)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")   # route template, not the raw URL
        elapsed = time.perf_counter() - start
        metrics.REQUESTS.labels(path=path, status=str(status)).inc()
        metrics.LATENCY.labels(path=path).observe(elapsed)
        if path not in ("/healthz", "/readyz", "/metrics"):
            log.info("request", extra={"path": path, "status": status,
                                       "ms": round(elapsed * 1000, 1)})
        request_id_var.reset(token)


app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(ask.router)

# Development only: `make dev` serves the chat UI from this process, so you can try it
# without a cluster. On Kubernetes the ui Deployment serves it and this stays unset.
_ui_dir = get_settings().serve_ui_dir
if _ui_dir:
    app.mount("/", StaticFiles(directory=_ui_dir, html=True), name="ui")
