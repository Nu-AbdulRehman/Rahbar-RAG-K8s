"""Generate, validate, retry once, fall back (section 3.4 and 3.2 steps 6-7).

The one place that handles a model misbehaving: a reply that is not valid JSON for the
Answer schema, a claim-bearing answer with no citation that matches what was retrieved,
a timeout, or a provider that is down. Each gets exactly one retry; after that the user
gets the canned answer, never a 5xx.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, replace

from pydantic import ValidationError

from ..providers.llm.base import LLMProvider, Prompt
from ..schemas import Answer, Citation, Passage

log = logging.getLogger("rahbar.generation")

FALLBACK = Answer(
    reasoning="fallback: no valid answer after one retry",
    answer="Sorry, I could not produce a reliable answer to that just now. "
           "Please try again, or rephrase the question.",
    citations=[], answered_from_context=False, confidence="low",
)


DECLINED = Answer(
    reasoning="the model found no answer in the evidence",
    answer="The documents I can search do not answer this question, so I cannot answer it "
           "from them. Please check with the relevant office.",
    citations=[], answered_from_context=False, confidence="low",
)


@dataclass
class Generated:
    answer: Answer
    fallback: bool          # True when the canned answer was returned
    attempts: int
    tokens_in: int = 0
    tokens_out: int = 0


def check_citations(answer: Answer, retrieved: list[Passage]) -> Answer:
    """Drop every citation that does not name a retrieved passage by source, section and
    page. Duplicates collapse. The model never decides what was retrieved."""
    allowed = {(p.source, p.section, p.page) for p in retrieved}
    kept: list[Citation] = []
    for c in answer.citations:
        if (c.source, c.section, c.page) in allowed and c not in kept:
            kept.append(c)
    dropped = len(answer.citations) - len(kept)
    if dropped:
        log.warning("citations dropped", extra={"dropped": dropped, "kept": len(kept)})
    return answer.model_copy(update={"citations": kept})


# "[source / section]" after a claim-bearing sentence (section 3.4). Only a marker naming
# a retrieved passage survives; the model never decides what was retrieved.
MARKER = re.compile(r"\s?\[([^\[\]/]+?) / ([^\[\]]+?)\]")


def check_markers(answer: Answer, retrieved: list[Passage]) -> Answer:
    """Remove inline markers that name nothing retrieved, and make sure an answer from
    context ends with at least one valid marker, built from its checked citations."""
    allowed = {(p.source, p.section) for p in retrieved}
    dropped = 0

    def keep(match: re.Match[str]) -> str:
        nonlocal dropped
        if (match[1].strip(), match[2].strip()) in allowed:
            return match[0]
        dropped += 1
        return ""

    text = MARKER.sub(keep, answer.answer).strip()
    if dropped:
        log.warning("inline citations dropped", extra={"dropped": dropped})
    if answer.answered_from_context and not MARKER.search(text):
        marks = dict.fromkeys(f"[{c.source} / {c.section}]" for c in answer.citations)
        text = f"{text} {' '.join(marks)}".strip()
    return answer.model_copy(update={"answer": text})


MIN_ATTEMPT_SECONDS = 1.0   # less time than this left: do not start another model call


def remaining(deadline: float | None) -> float | None:
    return None if deadline is None else deadline - time.monotonic()


def generate(provider: LLMProvider, prompt: Prompt, retrieved: list[Passage],
             deadline: float | None = None) -> Generated:
    """`deadline` is a time.monotonic() value: each attempt gets only the time left, and
    the retry is skipped when too little remains (Settings.request_budget)."""
    tokens_in = tokens_out = 0
    for attempt in (1, 2):                      # the first try and exactly one retry
        left = remaining(deadline)
        if left is not None and left < MIN_ATTEMPT_SECONDS:
            log.warning("request budget exhausted", extra={"attempt": attempt})
            break
        try:
            completion = provider.complete(prompt if left is None
                                           else replace(prompt, timeout=left))
            tokens_in += completion.tokens_in
            tokens_out += completion.tokens_out
            answer = check_citations(Answer.model_validate_json(completion.text), retrieved)
            if answer.answered_from_context and not answer.citations:
                raise ValueError("a claim-bearing answer has no valid citation")
            if not answer.answered_from_context:
                # The model says the evidence does not answer it. Its text is uncited by
                # definition, so the user sees the standard decline, never the model's guess.
                answer = DECLINED
            else:
                answer = check_markers(answer, retrieved)
            return Generated(answer, False, attempt, tokens_in, tokens_out)
        except (ValidationError, ValueError) as exc:
            log.warning("invalid model output", extra={"attempt": attempt,
                                                       "error": type(exc).__name__})
        except Exception as exc:  # timeout, connection refused, HTTP 5xx: never a 500
            log.warning("provider call failed", extra={"attempt": attempt,
                                                       "error": type(exc).__name__})
    return Generated(FALLBACK, True, 2, tokens_in, tokens_out)
