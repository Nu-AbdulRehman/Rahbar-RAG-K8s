"""Turns a question into an AskResponse: the query pipeline (section 3.2), in order.

1. validate      AskRequest (3-500 characters) rejects anything else with a 422
2. cache check   (section 3.3, providers/cache)
3. embed         inside the retriever, with the pinned EMBED_MODEL
4. retrieve      top_k, superseded documents excluded unless asked for (query.py)
5. floor         nothing at or above RELEVANCE_FLOOR: abstain, no generation call
6. augment       instructions, numbered evidence, question (prompt.py)
7. generate      validate, retry once, fall back, check citations (generation.py)
8. store         log the turn; cache it if safe
"""

from __future__ import annotations

import logging

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..schemas import Answer, AskResponse, Passage, RetrievedRef
from .generation import FALLBACK, Generated, generate
from .prompt import build_prompt
from .query import asks_about_older_version

log = logging.getLogger("rahbar.answer")

ABSTAIN = Answer(
    reasoning="abstained: no retrieved passage cleared the relevance floor",
    answer="The documents I can search do not cover this question, so I cannot answer it "
           "from them. Please check with the relevant office.",
    citations=[], answered_from_context=False, confidence="low",
)


def answer_question(
    question: str, retriever: Retriever, provider: LLMProvider, settings: Settings
) -> AskResponse:
    include_old = asks_about_older_version(question)
    try:
        passages = retriever.retrieve(question, k=settings.top_k,
                                      include_superseded=include_old)
    except Exception as exc:  # Chroma or the embedder down: degrade, never a 500
        log.warning("retrieval failed", extra={"error": type(exc).__name__})
        return _respond(Generated(FALLBACK, True, 0), [], provider, settings, include_old)

    evidence = [p for p in passages if p.score >= settings.relevance_floor]
    if not evidence:
        result = Generated(ABSTAIN, False, 0)
    else:
        prompt = build_prompt(question, evidence, settings.temperature)
        result = generate(provider, prompt, evidence)
    return _respond(result, passages, provider, settings, include_old,
                    abstained=not evidence)


def _respond(result: Generated, passages: list[Passage], provider: LLMProvider,
             settings: Settings, include_old: bool, abstained: bool = False) -> AskResponse:
    answer = result.answer
    log.info(
        "answered",
        extra={
            "provider": provider.name,
            "top_k": settings.top_k,
            "chunk_ids": [p.chunk_id for p in passages],
            "scores": [round(p.score, 4) for p in passages],
            "relevance_floor": settings.relevance_floor,
            "include_superseded": include_old,
            "abstained": abstained,
            "fallback": result.fallback,
            "attempts": result.attempts,
            "answered_from_context": answer.answered_from_context,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
        },
    )
    return AskResponse(
        request_id=request_id_var.get(),
        answer=answer.answer,                  # reasoning is never sent to the user
        citations=answer.citations,
        answered_from_context=answer.answered_from_context,
        confidence=answer.confidence,
        retrieved=[
            RetrievedRef(
                chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page, score=p.score
            )
            for p in passages
        ],
        provider=provider.name,
    )
