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
11. trace        one record per query, every step's values (services/trace.py, RAGOps D1)

The retrieval rail (guardrails.py, RAGOps D4) runs on the question at step 2 and on the
evidence between steps 7 and 8.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .. import timing
from ..config import Settings
from ..logjson import request_id_var
from ..providers.cache.semantic import NoCache, SemanticCache
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..routes import metrics
from ..schemas import Answer, AskResponse, Passage, RetrievedRef, Turn
from .conversation import context_block, is_follow_up, retrieval_query, updated_summary
from .generation import FALLBACK, Generated, generate, remaining
from .guardrails import check_passages, check_question
from .prompt import DELIMITERS, build_prompt
from .query import asks_about_older_version
from .trace import TraceSink, chunk_row, evidence_row, now, prompt_hash

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
    cache: SemanticCache | NoCache | None = None, sink: TraceSink | None = None,
) -> AskResponse:
    deadline = time.monotonic() + settings.request_budget   # retry and summary included
    begun = time.perf_counter()
    times = timing.start()
    history = history or []
    cache = cache or NoCache()
    follow_up = is_follow_up(question, history)
    query = retrieval_query(question, history) if follow_up else question
    if follow_up:
        metrics.FOLLOWUPS.inc()
    log.debug("conversation", extra={"history": [t.model_dump() for t in history],
                                     "summary": summary, "retrieval_query": query})
    record = _new_record(question, query if follow_up else None, retriever, provider, settings)
    for flag in check_question(question):
        metrics.INJECTIONS_FLAGGED.labels(source="question").inc()
        record["guardrails"].append({"name": "retrieval_rail", "action": "flagged",
                                     "source": "question", "pattern": flag.pattern})

    include_old = asks_about_older_version(query)
    # The cache is skipped both ways for follow-ups (their meaning depends on the
    # conversation) and for questions about an older version: cache entries are matched
    # on wording alone, and "the 2023 rules" and the current rules can be worded the
    # same. Standalone questions are keyed on the question alone, never on history.
    bypass = follow_up or include_old
    if bypass or not cache.enabled:
        metrics.record_cache_lookup("skipped")
    else:
        with timing.stage("cache"):
            hit, similarity = cache.lookup(question)
        metrics.record_cache_lookup("hit" if hit else "miss")
        record["cache"].update(lookup="hit" if hit else "miss", similarity=similarity)
        if hit:
            return _cached(hit, similarity, provider, summary, history, settings, deadline,
                           record, begun, sink)

    record["retrieval"]["filters"] = {
        "metadata": None if include_old else {"superseded": False},
        "include_superseded": include_old, "relevance_floor": settings.relevance_floor}
    abstained = False
    flagged_evidence = False
    prompt = None
    conversation = context_block(summary, history)
    started = time.perf_counter()
    try:
        passages = retriever.retrieve(query, k=settings.top_k, include_superseded=include_old)
    except Exception as exc:  # Chroma or the embedder down: degrade, never a 500
        log.warning("retrieval failed", extra={"error": type(exc).__name__})
        passages, result = [], Generated(FALLBACK, True, 0)
        metrics.FALLBACKS.labels(reason="retrieval").inc()
        record["guardrails"].append({"name": "fallback", "action": "returned the canned "
                                     "answer", "error": type(exc).__name__})
        record["outcome"] = "fallback"
    else:
        metrics.RETRIEVAL_LATENCY.observe(time.perf_counter() - started)
        record["retrieval"]["chunks"] = [chunk_row(i, p, settings.relevance_floor)
                                         for i, p in enumerate(passages, start=1)]
        if passages:
            metrics.TOP1_SIMILARITY.observe(max(p.score for p in passages))
        evidence = [p for p in passages if p.score >= settings.relevance_floor]
        evidence, flags = check_passages(evidence, settings.guardrail_injection_action)
        flagged_evidence = bool(flags)
        for flag in flags:
            metrics.INJECTIONS_FLAGGED.labels(source="chunk").inc()
            record["guardrails"].append({
                "name": "retrieval_rail", "source": "chunk", "chunk_id": flag.chunk_id,
                "pattern": flag.pattern,
                "action": "redacted" if settings.guardrail_injection_action == "redact"
                else "flagged; kept as delimited evidence"})
        # No reranker in this pipeline: the evidence goes into the prompt in the retriever's
        # order, minus what the floor removed. Recorded so a trace says so explicitly.
        record["retrieval"]["reranked_order"] = [p.chunk_id for p in evidence]
        if not evidence:
            abstained, result = True, Generated(ABSTAIN, False, 0)
            metrics.ABSTENTIONS.inc()
            record["outcome"] = "abstained"
        else:
            prompt = build_prompt(question, evidence, settings.temperature, conversation)
            log.debug("prompt", extra={"system": prompt.system, "user": prompt.user})
            stripped = _delimiters(question, evidence)
            if stripped:
                record["guardrails"].append({"name": "evidence_delimiters",
                                             "action": "stripped delimiter look-alikes",
                                             "count": stripped})
            started = time.perf_counter()
            with timing.stage("generate"):
                result = generate(provider, prompt, evidence, deadline)
            metrics.GENERATION_LATENCY.observe(time.perf_counter() - started)
            metrics.TOKENS.labels(direction="in").observe(result.tokens_in)
            metrics.TOKENS.labels(direction="out").observe(result.tokens_out)
            if result.fallback:
                metrics.FALLBACKS.labels(reason="generation").inc()
            record["guardrails"] += result.guardrails
            record["generation"].update(
                prompt_hash=prompt_hash(prompt), attempts=result.attempts,
                fallback=result.fallback, tokens_in=result.tokens_in,
                tokens_out=result.tokens_out)
            record["outcome"] = ("fallback" if result.fallback else "answered"
                                 if result.answer.answered_from_context else "declined")

    with timing.stage("summary"):
        new_summary, summary_failed = updated_summary(provider, summary, history,
                                                      settings.history_turns,
                                                      settings.temperature, remaining(deadline))
    if summary_failed:
        metrics.SUMMARY_FAILURES.inc()

    answer = result.answer
    # Never cache a follow-up, an old-version question, an abstention, an out-of-scope
    # answer, a fallback, anything without a valid citation, or an answer built on evidence
    # the retrieval rail flagged: a cached mistake is served to everyone (3.3), and a
    # change of GUARDRAIL_INJECTION_ACTION does not invalidate the cache (failure-log).
    safe = (not bypass and not abstained and not result.fallback and not flagged_evidence
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
    record["cache"]["stored"] = bool(stored)
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
    if prompt is not None:
        record["prompt"] = {"system": prompt.system, "user": prompt.user}
        record["evidence"] = [evidence_row(p) for p in prompt.passages]
        record["conversation"] = conversation
    _finish(record, response, times, begun, sink)
    return response


def _new_record(question: str, rewritten: str | None, retriever: Retriever,
                provider: LLMProvider, settings: Settings) -> dict[str, Any]:
    """The trace record's skeleton (services/trace.py lists every field)."""
    embedder = getattr(retriever, "embedder", None)
    return {
        "trace_id": request_id_var.get(), "timestamp": now(), "pod": settings.pod_name,
        "query": question, "rewritten_query": rewritten, "follow_up": rewritten is not None,
        "embedding": {"model": settings.embed_model,
                      "version": getattr(embedder, "digest", None),
                      "dimension": getattr(embedder, "dimension", None)},
        "collection": settings.collection if retriever.name == "chroma" else retriever.name,
        "retrieval": {"retriever": retriever.name, "top_k": settings.top_k, "filters": None,
                      "chunks": [], "reranker": "none", "reranked_order": []},
        "generation": {"provider": provider.name, "model": settings.llm_model,
                       "parameters": {"temperature": settings.temperature,
                                      "seed": settings.llm_seed,
                                      "output": "Answer JSON schema"},
                       "prompt_hash": None, "attempts": 0, "fallback": False,
                       "tokens_in": 0, "tokens_out": 0},
        "response": None, "outcome": None, "guardrails": [],
        "cache": {"lookup": "skipped", "similarity": None, "stored": False},
        "latency_ms": {},
    }


def _finish(record: dict[str, Any], response: AskResponse, times: dict[str, float],
            begun: float, sink: TraceSink | None) -> None:
    record["response"] = {"answer": response.answer,
                          "answered_from_context": response.answered_from_context,
                          "confidence": response.confidence,
                          "citations": [c.model_dump() for c in response.citations],
                          "cached": response.cached}
    for stage_name, ms in times.items():
        metrics.STAGE_LATENCY.labels(stage=stage_name).observe(ms / 1000)
    record["latency_ms"] = {**times, "total": round((time.perf_counter() - begun) * 1000, 1)}
    (sink or DEFAULT_SINK).write(record)


def _delimiters(question: str, evidence: list[Passage]) -> int:
    """Delimiter look-alikes build_prompt strips from the question and the evidence."""
    texts = [question] + [t for p in evidence for t in (p.text, p.source, p.section)]
    return sum(len(DELIMITERS.findall(t)) for t in texts)


DEFAULT_SINK = TraceSink()


# What a cache entry holds: the answer, never the request id or the conversation.
CACHED_FIELDS = {"answer", "citations", "answered_from_context", "confidence", "retrieved",
                 "provider"}


def _cached(hit: dict, similarity: float, provider: LLMProvider, summary: str,
            history: list[Turn], settings: Settings, deadline: float,
            record: dict[str, Any], begun: float, sink: TraceSink | None) -> AskResponse:
    times = timing.stage_times.get() or {}
    with timing.stage("summary"):
        new_summary, summary_failed = updated_summary(provider, summary, history,
                                                      settings.history_turns,
                                                      settings.temperature, remaining(deadline))
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
    # A hit has no retrieval of its own: the trace shows the chunks the cached answer was
    # built from, as the cache stored them, and no prompt.
    record["retrieval"]["chunks"] = [
        {"rank": i, **r.model_dump(), "from_cache": True}
        for i, r in enumerate(response.retrieved, start=1)]
    record["outcome"] = "cached"
    _finish(record, response, times, begun, sink)
    return response


def _ref(p: Passage) -> RetrievedRef:
    return RetrievedRef(chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page,
                        score=p.score)
