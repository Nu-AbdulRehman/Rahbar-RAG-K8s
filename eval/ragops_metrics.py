"""Pure metric functions for the RAGOps test suite (Part B). No network, no model: the
suite (eval/suite.py) gathers the data, these turn it into numbers.

Relevance is matched on (source, normalised section), exactly as eval/run_eval.py does,
so the A02 numbers and these stay comparable.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

from run_eval import _key  # (source, normalised section)


def _relevant_keys(relevant: list[dict]) -> set[tuple[str, str]]:
    return {_key(r) for r in relevant}


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    wanted = _relevant_keys(relevant)
    if not wanted:
        return None
    return len(wanted & {_key(r) for r in retrieved[:k]}) / len(wanted)


def reciprocal_rank(relevant: list[dict], retrieved: list[dict]) -> float | None:
    """1 / rank of the first relevant passage; 0 when none is retrieved."""
    wanted = _relevant_keys(relevant)
    if not wanted:
        return None
    for rank, passage in enumerate(retrieved, start=1):
        if _key(passage) in wanted:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Binary-relevance nDCG@k. A relevant (source, section) counts once, at its first
    rank, so two chunks of one section do not double the gain."""
    wanted = _relevant_keys(relevant)
    if not wanted:
        return None
    seen: set[tuple[str, str]] = set()
    dcg = 0.0
    for rank, passage in enumerate(retrieved[:k], start=1):
        key = _key(passage)
        if key in wanted and key not in seen:
            seen.add(key)
            dcg += 1.0 / math.log2(rank + 1)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(wanted), k) + 1))
    return dcg / ideal


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def max_abs_diff(a: Sequence[float], b: Sequence[float]) -> float:
    return max((abs(x - y) for x, y in zip(a, b)), default=0.0)


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100
    low, high = math.floor(pos), math.ceil(pos)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def mean(values: list[float | None]) -> float | None:
    scored = [v for v in values if v is not None]
    return round(sum(scored) / len(scored), 4) if scored else None


def add_typos(text: str, rng: random.Random, rate: float = 0.15) -> str:
    """The noise test's query perturbation: in about `rate` of the words longer than three
    letters, swap two neighbouring letters. Seeded, so both suite runs see the same typos."""
    words = text.split(" ")
    for i, word in enumerate(words):
        if len(word) > 3 and word.isalpha() and rng.random() < rate:
            j = rng.randrange(1, len(word) - 2)
            words[i] = word[:j] + word[j + 1] + word[j] + word[j + 2:]
    return " ".join(words)


def diff(first: dict, second: dict, prefix: str = "") -> dict[str, float]:
    """Every numeric leaf that differs between two result dicts, as second - first."""
    out: dict[str, float] = {}
    for key, a in first.items():
        b = second.get(key)
        name = f"{prefix}{key}"
        if isinstance(a, dict) and isinstance(b, dict):
            out.update(diff(a, b, name + "."))
        elif isinstance(a, int | float) and isinstance(b, int | float) \
                and not isinstance(a, bool):
            out[name] = round(b - a, 4)
    return out
