"""RAGOps E2/E4: coverage is the share of live queries whose nearest golden question
clears the threshold, and the check fails below the minimum share."""

from __future__ import annotations

from pathlib import Path

from query_coverage import nearest, report

GOLDEN = [{"id": "q1", "question": "attendance rule"}, {"id": "q2", "question": "fee per credit"}]
LIVE = [{"id": "l1", "query": "how many classes can I miss", "topic": "attendance"},
        {"id": "l2", "query": "tuition per credit hour", "topic": "fees"},
        {"id": "l3", "query": "library fine", "topic": "library"},
        {"id": "l4", "query": "books I can borrow", "topic": "library"}]


def test_nearest_picks_the_most_similar_golden_vector() -> None:
    golden = [[1.0, 0.0], [0.0, 1.0]]
    assert nearest([[0.9, 0.1], [0.1, 0.9]], golden)[0][0] == 0
    assert nearest([[0.9, 0.1], [0.1, 0.9]], golden)[1][0] == 1


def test_report_groups_uncovered_queries_and_fails_below_the_minimum() -> None:
    matches = [(0, 0.91), (1, 0.88), (0, 0.41), (1, 0.39)]
    result = report(LIVE, GOLDEN, matches, threshold=0.8, min_share=0.85)
    assert result["coverage"] == 0.5 and result["passed"] is False
    assert result["uncovered_by_topic"] == {"library": ["library fine", "books I can borrow"]}
    closed = report(LIVE, GOLDEN, [(0, 0.91), (1, 0.88), (0, 0.85), (1, 0.82)], 0.8, 0.85)
    assert closed["passed"] is True and closed["uncovered_by_topic"] == {}


def test_without_category_leaves_those_golden_questions_out(tmp_path, monkeypatch) -> None:
    """The E screenshot's 'before': the same run without E4's coverage_gap questions."""
    import json
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
    import app.providers.llm.embed as embed
    import query_coverage

    class Fake:
        def __init__(self, settings) -> None:
            pass

        def embed(self, text: str) -> list[float]:
            return [1.0, 0.0] if "library" in text or "borrow" in text else [0.0, 1.0]

    monkeypatch.setattr(embed, "OllamaEmbedder", Fake)
    live, golden = tmp_path / "live.jsonl", tmp_path / "golden.jsonl"
    live.write_text(json.dumps({"id": "l1", "query": "books I can borrow", "topic": "library"}))
    golden.write_text(json.dumps({"id": "q1", "question": "fee per credit", "category": "ordinary"})
                      + "\n" + json.dumps({"id": "q2", "question": "library loans",
                                           "category": "coverage_gap"}))
    common = ["--live", str(live), "--golden", str(golden), "--out-dir", str(tmp_path)]
    assert query_coverage.main(common) == 0                                     # q2 covers it
    assert query_coverage.main(common + ["--without-category", "coverage_gap"]) == 1
