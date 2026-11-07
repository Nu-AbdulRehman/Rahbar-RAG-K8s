"""The request budget (§3.4, §4.1): /api/ask finishes before the Ingress gives up, so a slow
model ends in our canned answer, never the Ingress's 504. A fake clock: no sleeping."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.providers.llm.base import Completion, Prompt
from app.schemas import Passage, Turn
from app.services.answer import answer_question
from app.services.generation import FALLBACK

PASSAGE = Passage(chunk_id="hb#1", source="hb.pdf", section="Attendance Requirements",
                  page=10, score=0.8, text="1.21 Students are required to attend 100%.")
GOOD = json.dumps({"reasoning": "r", "answer": "100%.", "answered_from_context": True,
                   "confidence": "high",
                   "citations": [{"source": "hb.pdf", "section": "Attendance Requirements",
                                  "page": 10}]})


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(time, "monotonic", c)
    return c


class SlowProvider:
    """Each call takes `cost` seconds of fake time; records the timeout it was given."""

    name = "slow"

    def __init__(self, clock: Clock, cost: float, fail: bool) -> None:
        self.clock, self.cost, self.fail = clock, cost, fail
        self.timeouts: list[float | None] = []

    def complete(self, prompt: Prompt) -> Completion:
        self.timeouts.append(prompt.timeout)
        self.clock.now += self.cost
        if self.fail:
            raise httpx.ReadTimeout("model still loading")
        if "answer" not in prompt.schema["properties"]:
            return Completion(json.dumps({"summary": "new"}))
        return Completion(GOOD)


class Fixed:
    name = "fixed"

    def retrieve(self, question: str, k: int, include_superseded: bool = False) -> list:
        return [PASSAGE]


SETTINGS = Settings(relevance_floor=0.5, request_budget=50.0, history_turns=1)


def test_each_call_gets_only_the_time_left(clock: Clock) -> None:
    provider = SlowProvider(clock, cost=20.0, fail=True)
    answer_question("What attendance is required?", Fixed(), provider, SETTINGS)
    assert provider.timeouts == [50.0, 30.0]                 # the retry gets the rest


def test_no_retry_once_the_budget_is_spent(clock: Clock) -> None:
    provider = SlowProvider(clock, cost=49.5, fail=True)
    response = answer_question("What attendance is required?", Fixed(), provider, SETTINGS)
    assert len(provider.timeouts) == 1
    assert response.answer == FALLBACK.answer


def test_the_summary_is_skipped_when_no_time_is_left(clock: Clock) -> None:
    provider = SlowProvider(clock, cost=49.5, fail=False)
    response = answer_question("What attendance is required?", Fixed(), provider, SETTINGS,
                               history=[Turn(question="q?", answer="a")], summary="old")
    assert response.answered_from_context is True             # the answer still arrives
    assert response.summary == "old" and len(provider.timeouts) == 1


def test_ollama_sends_the_budgeted_timeout_to_httpx() -> None:
    from app.providers.llm.ollama import OllamaProvider
    from app.services.prompt import build_prompt

    seen: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json={"message": {"content": GOOD}})

    provider = OllamaProvider(Settings(), httpx.Client(transport=httpx.MockTransport(handler),
                                                       timeout=60.0))
    prompt = build_prompt("q?", [PASSAGE], 0.2)
    provider.complete(prompt)
    from dataclasses import replace
    provider.complete(replace(prompt, timeout=12.5))
    assert seen[0]["read"] == 60.0 and seen[1]["read"] == 12.5
