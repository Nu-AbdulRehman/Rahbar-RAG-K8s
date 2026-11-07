"""Turns a question into an AskResponse: the query pipeline (section 3.2), in order.

1. validate      AskRequest (3-500 characters, capped history) rejects the rest with a 422
2. follow-up     only with browser history (conversation.py, ADR 0002)
3. cache check   skipped for follow-ups (section 3.3, providers/cache)
4. rewrite       a follow-up is retrieved with a standalone query
5. embed         inside the retriever, with the pinned EMBED_MODEL
6. retrieve      top_k, superseded documents excluded unless asked for (query.py)
7. floor         nothing at or above RELEVANCE_FLOOR: abstain, no generation call
8. augment       instructions, conversation, numbered evidence, question (prompt.py)
9. generate      validate, retry once, fall back, check citations (generation.py)
10. store        log the turn; cache it if safe; return the updated summary
"""

from __future__ import annotations

import logging
import time

from ..config import Settings
from ..logjson import request_id_var
from ..providers.cache.semantic import NoCache, SemanticCache
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..routes import metrics
from ..schemas import Answer, AskResponse, Passage, RetrievedRef, Turn
from .conversation import context_block, is_follow_up, retrieval_query, updated_summary
from .generation import FALLBACK, Generated, generate, remaining
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
    question: str, retriever: Retriever, provider: LLMProvider, settings: Settings,
    history: list[Turn] | None = None, summary: str = "",
    cache: SemanticCache | NoCache | None = None,
) -> AskResponse:
    deadline = time.monotonic() + settings.request_budget   # retry and summary included
    history = history or []
    cache = cache or NoCache()
    follow_up = is_follow_up(question, history)
    query = retrieval_query(question, history) if follow_up else question
    if follow_up:
        metrics.FOLLOWUPS.inc()
    log.debug("conversation", extra={"history": [t.model_dump() for t in history],
                                     "summary": summary, "retrieval_query": query})

    include_old = asks_about_older_version(query)
    # The cache is skipped both ways for follow-ups (their meaning depends on the
    # conversation) and for questions about an older version: cache entries are matched
    # on wording alone, and "the 2023 rules" and the current rules can be worded the
    # same. Standalone questions are keyed on the question alone, never on history.
    bypass = follow_up or include_old
    if bypass or not cache.enabled:
        metrics.record_cache_lookup("skipped")
    else:
        hit, similarity = cache.lookup(question)
        metrics.record_cache_lookup("hit" if hit else "miss")
        if hit:
            return _cached(hit, similarity, provider, summary, history, settings, deadline)

    abstained = False
    started = time.perf_counter()
    try:
        passages = retriever.retrieve(query, k=settings.top_k, include_superseded=include_old)
    except Exception as exc:  # Chroma or the embedder down: degrade, never a 500
        log.warning("retrieval failed", extra={"error": type(exc).__name__})
        passages, result = [], Generated(FALLBACK, True, 0)
        metrics.FALLBACKS.labels(reason="retrieval").inc()
    else:
        metrics.RETRIEVAL_LATENCY.observe(time.perf_counter() - started)
        evidence = [p for p in passages if p.score >= settings.relevance_floor]
        if not evidence:
            abstained, result = True, Generated(ABSTAIN, False, 0)
            metrics.ABSTENTIONS.inc()
        else:
            prompt = build_prompt(question, evidence, settings.temperature,
                                  context_block(summary, history))
            log.debug("prompt", extra={"system": prompt.system, "user": prompt.user})
            started = time.perf_counter()
            result = generate(provider, prompt, evidence, deadline)
            metrics.GENERATION_LATENCY.observe(time.perf_counter() - started)
            metrics.TOKENS.labels(direction="in").observe(result.tokens_in)
            metrics.TOKENS.labels(direction="out").observe(result.tokens_out)
            if result.fallback:
                metrics.FALLBACKS.labels(reason="generation").inc()

    new_summary, summary_failed = updated_summary(provider, summary, history,
                                                  settings.history_turns, settings.temperature,
                                                  remaining(deadline))
    if summary_failed:
        metrics.SUMMARY_FAILURES.inc()

    answer = result.answer
    # Never cache a follow-up, an old-version question, an abstention, an out-of-scope
    # answer, a fallback, or anything without a valid citation: a cached mistake is
    # served to everyone (3.3).
    safe = (not bypass and not abstained and not result.fallback
            and answer.answered_from_context and bool(answer.citations))
    response = AskResponse(
        request_id=request_id_var.get(),
        answer=answer.answer,                  # reasoning is never sent to the user
        citations=answer.citations,
        answered_from_context=answer.answered_from_context,
        confidence=answer.confidence,
        retrieved=[_ref(p) for p in passages],
        provider=provider.name,
        summary=new_summary,
        history_turns=settings.history_turns,
    )
    stored = safe and cache.store(question, response.model_dump(include=CACHED_FIELDS))
    if stored:
        metrics.CACHE_STORES.inc()
    log.info(
        "answered",
        extra={
            "provider": provider.name,
            "top_k": settings.top_k,
            "chunk_ids": [p.chunk_id for p in passages],
            "scores": [round(p.score, 4) for p in passages],
            "relevance_floor": settings.relevance_floor,
            "include_superseded": include_old,
            "follow_up": follow_up,
            "history_turns": len(history),
            "abstained": abstained,
            "fallback": result.fallback,
            "attempts": result.attempts,
            "answered_from_context": answer.answered_from_context,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "summary_failed": summary_failed,
            "cached": False,
            "cache_stored": stored,
        },
    )
    return response


# What a cache entry holds: the answer, never the request id or the conversation.
CACHED_FIELDS = {"answer", "citations", "answered_from_context", "confidence", "retrieved",
                 "provider"}


def _cached(hit: dict, similarity: float, provider: LLMProvider, summary: str,
            history: list[Turn], settings: Settings, deadline: float) -> AskResponse:
    new_summary, summary_failed = updated_summary(provider, summary, history,
                                                  settings.history_turns, settings.temperature,
                                                  remaining(deadline))
    if summary_failed:
        metrics.SUMMARY_FAILURES.inc()
    response = AskResponse(**hit, request_id=request_id_var.get(), summary=new_summary,
                           history_turns=settings.history_turns, cached=True)
    log.info("answered", extra={
        "cached": True, "cache_similarity": similarity, "top_k": settings.top_k,
        "chunk_ids": [r.chunk_id for r in response.retrieved],
        "scores": [r.score for r in response.retrieved], "abstained": False,
        "follow_up": False, "answered_from_context": response.answered_from_context,
    })
    return response


def _ref(p: Passage) -> RetrievedRef:
    return RetrievedRef(chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page,
                        score=p.score)
