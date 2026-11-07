"""The contracts. Change them only with your partner's review: the UI, the
evaluation script and your tests all depend on these shapes.

`Answer` is what the model must produce (section 3.4). `AskResponse` is what
the API returns to the UI and to eval/run_eval.py. The model's `reasoning` is
never sent to the user.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


# Size caps for the browser-held conversation (ADR 0002). The window length itself,
# HISTORY_TURNS, comes from the ConfigMap and is checked in routes/ask.py.
MAX_HISTORY_ANSWER = 2000
MAX_SUMMARY = 1500
MAX_HISTORY_TURNS = 10      # hard ceiling for the schema; HISTORY_TURNS must not exceed it


class Turn(BaseModel):
    """One earlier exchange, as the browser stored it: never reasoning or retrieved text."""

    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(max_length=MAX_HISTORY_ANSWER)


class AskRequest(BaseModel):
    # Surrounding whitespace is stripped before the 3-500 check, so "   " is a 422.
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3,
                                               max_length=500)]
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    summary: str = Field(default="", max_length=MAX_SUMMARY)


class Passage(BaseModel):
    """One retrieved chunk, as the retriever hands it to the generator."""

    chunk_id: str
    text: str
    source: str
    section: str
    page: int | None = None
    score: float = Field(description="Similarity, higher is closer (1 - cosine distance).")


class Citation(BaseModel):
    source: str
    section: str
    page: int | None = None


class Answer(BaseModel):
    """The model's output contract. Send its JSON schema to the model, then validate."""

    reasoning: str
    answer: str
    citations: list[Citation]
    answered_from_context: bool
    confidence: Literal["high", "medium", "low"]


class RetrievedRef(BaseModel):
    """What the response says was retrieved. eval/run_eval.py scores against this."""

    chunk_id: str
    source: str
    section: str
    page: int | None = None
    score: float


class AskResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[Citation]
    answered_from_context: bool
    confidence: Literal["high", "medium", "low"]
    retrieved: list[RetrievedRef]
    provider: str
    # ADR 0002: the conversation summary to send back next time, and the window size.
    summary: str = ""
    history_turns: int = 3
    cached: bool = False             # served from the semantic cache (section 3.3)


class Summary(BaseModel):
    """The model's output when it folds an old turn into the conversation summary."""

    summary: str
