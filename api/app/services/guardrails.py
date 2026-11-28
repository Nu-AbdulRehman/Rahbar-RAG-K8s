"""The retrieval rail (RAGOps D4): instruction-like text in a retrieved chunk or in the
question is flagged, counted and written into the trace.

It sits in front of the Assignment 02 injection defence, which stays as it was: evidence
delimited and numbered after the instructions (prompt.py), delimiter look-alikes stripped,
citations and inline markers that name nothing retrieved dropped, and an uncited answer
replaced by the standard decline (generation.py). Those steps report what they did into
the same trace, so one record shows every guardrail that acted on a query.

GUARDRAIL_INJECTION_ACTION (ConfigMap) decides what the rail does to a flagged chunk:
    flag     keep the chunk as delimited evidence and record it (the default: the
             Assignment 02 defence then has to hold on its own, which the poisoned-chunk
             test proves, and a true passage that merely mentions "instructions" loses
             nothing)
    redact   also cut the flagged sentences out of the chunk before it reaches the prompt
A flagged question is never changed: it is the user's own text, already delimited as data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas import Passage

# Phrases that address the model rather than inform a reader. Each one is a known
# injection opener; ordinary policy text ("follow the instructions on the exam paper")
# does not match, because every pattern needs the override or role-change wording.
PATTERNS: dict[str, re.Pattern[str]] = {
    # "ignore all previous instructions", "disregard your rules"; never "do not ignore
    # the rules", which needs a qualifier that points back at the model's own instructions
    "ignore-instructions": re.compile(
        r"\b(ignore|disregard|forget|override)\s+(all\s+|any\s+)?(of\s+)?(the\s+)?"
        r"((previous|prior|above|earlier|preceding|system|original|your)\s+){1,2}"
        r"(instructions?|rules|prompts?|directions|guidelines)\b"
        r"|\b(ignore|disregard)\s+(all|any)\s+(instructions?|prompts?)\b", re.I),
    "role-change": re.compile(r"\byou\s+are\s+now\s+(the|a|an|my)\b", re.I),
    "system-prompt": re.compile(r"\b(system\s+prompt|developer\s+message)\b|^\s*system\s*:",
                                re.I | re.M),
    "new-instructions": re.compile(r"\b(new|updated)\s+instructions?\s*:", re.I),
    "tell-every-user": re.compile(r"\btell\s+(every|all|each)\s+(student|user)s?\s+that\b",
                                  re.I),
}
SENTENCE = re.compile(r"(?<=[.!?])\s+")
ACTIONS = ("flag", "redact")


@dataclass
class Flag:
    source: str            # "chunk" or "question"
    pattern: str
    chunk_id: str | None = None


def scan(text: str) -> list[str]:
    """Names of the patterns that match, in PATTERNS order."""
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]


def redact(text: str) -> str:
    """Remove every sentence that matches a pattern; the rest of the chunk stays."""
    kept = [s for s in SENTENCE.split(text) if not scan(s)]
    return " ".join(kept).strip() or "[removed by the retrieval rail]"


def check_question(question: str) -> list[Flag]:
    return [Flag("question", name) for name in scan(question)]


def check_passages(passages: list[Passage], action: str) -> tuple[list[Passage], list[Flag]]:
    """The passages to put in the prompt, and one Flag per (chunk, pattern) found."""
    if action not in ACTIONS:
        raise ValueError(f"GUARDRAIL_INJECTION_ACTION must be one of {ACTIONS}, got {action!r}")
    flags: list[Flag] = []
    out: list[Passage] = []
    for p in passages:
        found = scan(p.text)
        flags += [Flag("chunk", name, p.chunk_id) for name in found]
        out.append(p.model_copy(update={"text": redact(p.text)})
                   if found and action == "redact" else p)
    return out, flags
