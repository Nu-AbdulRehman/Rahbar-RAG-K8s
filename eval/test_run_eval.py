"""Checks for the scoring and the gate (§5.2-§5.4). No API, no network."""

from __future__ import annotations

from run_eval import citation_validity, gate, recall_at_k, summarise

A = {"source": "a.pdf", "section": "Attendance Requirements", "page": 10}
B = {"source": "a.pdf", "section": "Academic Warning/Probation", "page": 24}
C = {"source": "b.html", "section": "Fee Refund Policy", "page": 1}


def test_recall_matches_normalised_sections_within_k() -> None:
    relevant = [{"source": "a.pdf", "section": "attendance  requirements."}, B]
    assert recall_at_k(relevant, [C, A, B], 2) == 0.5
    assert recall_at_k(relevant, [C, A, B], 3) == 1.0
    assert recall_at_k([], [A], 5) is None


def test_citation_validity_needs_source_section_and_page() -> None:
    wrong_page = {**A, "page": 11}
    assert citation_validity({"citations": [A, wrong_page], "retrieved": [A]}) == 0.5
    assert citation_validity({"citations": [], "retrieved": [A]}) is None


def _row(qid: str, kind: str, response: dict, relevant: list | None = None,
         abstain: bool = False) -> dict:
    return {"id": qid, "type": kind, "must_abstain": abstain, "relevant": relevant or [],
            "response": {"retrieved": [], "citations": [], **response}}


def test_gate_passes_a_healthy_run_and_names_each_failure() -> None:
    good = [_row("q1", "ordinary", {"retrieved": [A], "citations": [A],
                                    "answered_from_context": True}, [A]),
            _row("q2", "abstain", {"answered_from_context": False}, abstain=True)]
    results = summarise(good)
    assert results["recall@5"] == 1.0 and results["abstention_correctness"] == 1.0
    assert results["by_type"]["ordinary"]["recall@5"] == 1.0
    assert gate(results, {"recall@5": 1.0}) == []

    bad = [_row("q1", "ordinary", {"retrieved": [C], "citations": [A],
                                   "answered_from_context": True}, [A]),
           _row("q2", "abstain", {"answered_from_context": True}, abstain=True)]
    failures = gate(summarise(bad), {"recall@5": 1.0})
    assert len(failures) == 3
    assert any("recall@5" in f for f in failures)
    assert any("q2" in f for f in failures)
    assert any("citation validity" in f for f in failures)


def test_gate_allows_a_drop_of_exactly_five_points() -> None:
    assert gate({"recall@5": 0.75, "citation_validity": 1.0, "per_question": []},
                {"recall@5": 0.80}) == []


def test_follow_ups_are_reported_but_kept_out_of_the_gate() -> None:
    rows = [_row("q1", "ordinary", {"retrieved": [A], "citations": [A],
                                    "answered_from_context": True}, [A]),
            _row("q2", "followup", {"retrieved": [C], "citations": [B],
                                    "answered_from_context": True}, [A])]
    results = summarise(rows)
    assert results["recall@5"] == 1.0 and results["citation_validity"] == 1.0
    assert results["by_type"]["followup"]["recall@5"] == 0.0
    assert gate(results, {"recall@5": 1.0}) == []
