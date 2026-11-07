"""One JSON line per request with what diagnosis needs, and the §4.8 metrics. Stubs only."""

from __future__ import annotations

import io
import json
import logging

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    from app.main import app

    with TestClient(app) as c:
        yield c


def _lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.startswith("{")]


def test_one_answer_line_per_request_with_ids_scores_and_abstention(client: TestClient) -> None:
    from app.logjson import JsonFormatter

    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(JsonFormatter())           # the formatter the pods use
    logging.getLogger().addHandler(handler)
    try:
        client.post("/api/ask", json={"question": "What is the attendance rule?"},
                    headers={"X-Request-ID": "obs-1"})
    finally:
        logging.getLogger().removeHandler(handler)
    lines = [e for e in _lines(out.getvalue()) if e["request_id"] == "obs-1"]
    answered = [e for e in lines if e["msg"] == "answered"]
    assert len(answered) == 1
    line = answered[0]
    assert line["top_k"] == 5 and line["chunk_ids"] == ["stub-001", "stub-002", "stub-003"]
    assert line["scores"] == [0.91, 0.84, 0.77] and line["abstained"] is False
    assert all("user" not in e and "system" not in e for e in lines)   # prompt: DEBUG only


def test_the_section_4_8_metrics_are_exposed(client: TestClient,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    client.post("/api/ask", json={"question": "What is the attendance rule?"})
    client.app.state.settings = client.app.state.settings.__class__(   # type: ignore[attr-defined]
        relevance_floor=0.99)
    client.post("/api/ask", json={"question": "How do I apply for a hostel room?"})
    text = client.get("/metrics").text
    for name in ("rahbar_requests_total", "rahbar_request_seconds_bucket",
                 "rahbar_retrieval_seconds_count", "rahbar_generation_seconds_count",
                 'rahbar_tokens_per_request_count{direction="in"}',
                 'rahbar_tokens_per_request_count{direction="out"}',
                 "rahbar_abstentions_total", "rahbar_cache_hit_ratio",
                 "rahbar_cache_lookups_total"):
        assert name in text, name
    abstentions = [line for line in text.splitlines()
                   if line.startswith("rahbar_abstentions_total ")]
    assert float(abstentions[0].split()[1]) >= 1
