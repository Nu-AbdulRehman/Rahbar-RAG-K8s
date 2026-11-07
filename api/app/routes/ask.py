"""POST /api/ask. The Ingress sends /api/* here unchanged, so the prefix stays."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import AskRequest, AskResponse
from ..services.answer import answer_question

router = APIRouter(prefix="/api")


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request) -> AskResponse:
    state = request.app.state
    if len(body.history) > state.settings.history_turns:
        raise HTTPException(422, f"history holds at most {state.settings.history_turns} turns")
    return answer_question(body.question, state.retriever, state.provider, state.settings,
                           history=body.history, summary=body.summary, cache=state.cache)
