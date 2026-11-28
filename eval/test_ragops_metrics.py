"""The Part B metrics on hand-made rankings, with the expected values worked out by hand."""

from __future__ import annotations

import math
import random

import pytest

from ragops_metrics import (
    add_typos,
    cosine,
    diff,
    max_abs_diff,
    ndcg_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
)

A = {"source": "h.pdf", "section": "Attendance"}
B = {"source": "h.pdf", "section": "Warning"}
X = {"source": "x.pdf", "section": "Other"}


def test_reciprocal_rank() -> None:
    assert reciprocal_rank([A], [X, X, A]) == pytest.approx(1 / 3)
    assert reciprocal_rank([A], [A, X]) == 1.0
    assert reciprocal_rank([A], [X, X]) == 0.0
    assert reciprocal_rank([], [A]) is None                   # unanswerable: not scored


def test_ndcg_rewards_rank_and_counts_a_section_once() -> None:
    assert ndcg_at_k([A], [A, X], 5) == 1.0
    assert ndcg_at_k([A], [X, A], 5) == pytest.approx(1 / math.log2(3))
    # two relevant sections, found at ranks 1 and 3; the ideal has them at 1 and 2
    ideal = 1 + 1 / math.log2(3)
    assert ndcg_at_k([A, B], [A, X, B], 5) == pytest.approx((1 + 0.5) / ideal)
    # a repeated chunk of the same section adds nothing
    assert ndcg_at_k([A], [A, A], 5) == 1.0
    assert ndcg_at_k([A], [X, X, X, X, X, A], 5) == 0.0      # outside the top 5


def test_recall_at_k_matches_sections_case_insensitively() -> None:
    assert recall_at_k([A, B], [{"source": "h.pdf", "section": "attendance."}, X], 3) == 0.5


def test_cosine_and_determinism_helpers() -> None:
    assert cosine([1, 0], [1, 0]) == 1.0
    assert cosine([1, 0], [0, 1]) == 0.0
    assert max_abs_diff([0.1, 0.2], [0.1, 0.25]) == pytest.approx(0.05)


def test_percentile_interpolates() -> None:
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([5.0], 95) == 5.0
    assert percentile([], 95) is None


def test_typos_are_seeded_and_keep_word_count() -> None:
    text = "What happens if a student misses the attendance requirement"
    one, two = add_typos(text, random.Random(7)), add_typos(text, random.Random(7))
    assert one == two and one != text
    assert len(one.split()) == len(text.split())


def test_diff_walks_nested_results() -> None:
    first = {"component": {"recall@5": 0.9, "n": 20}, "label": "a", "ok": True}
    second = {"component": {"recall@5": 0.85, "n": 20}, "label": "b", "ok": False}
    assert diff(first, second) == {"component.recall@5": -0.05, "component.n": 0}
