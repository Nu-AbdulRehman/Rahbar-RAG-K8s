"""Input and configuration validation (§3.2 step 1, §3.4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("question", ["   ", " \n\t ", "  a  "])
def test_whitespace_does_not_count_towards_the_minimum(client: TestClient,
                                                       question: str) -> None:
    assert client.post("/api/ask", json={"question": question}).status_code == 422


def test_a_padded_question_is_accepted_and_stripped(client: TestClient) -> None:
    r = client.post("/api/ask", json={"question": "   What is the attendance rule?   "})
    assert r.status_code == 200


@pytest.mark.parametrize("temperature", [-0.1, 0.31, 1.2])
def test_temperature_outside_0_to_0_3_is_refused(temperature: float) -> None:
    with pytest.raises(ValueError, match="TEMPERATURE"):
        Settings(temperature=temperature)


def test_the_api_refuses_to_start_at_temperature_1_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPERATURE", "1.2")
    from app.main import app

    with pytest.raises(ValueError, match="TEMPERATURE"), TestClient(app):
        pass
