#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails, 2 when a scoring function is
not implemented. CI relies on that exit code.

Sections are matched by (source, normalised heading); see docs/PIPELINE.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent

# The gate from section 5.4. Change these only with a reason written in docs/PIPELINE.md.
MAX_RECALL5_DROP = 0.05        # recall@5 may fall at most 5 points below the baseline
MIN_CITATION_VALIDITY = 0.95   # at least 95% of citations must match retrieved passages
REQUIRED_ABSTENTION = 1.0      # every must-abstain question must be declined


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    if not questions:
        sys.exit(f"no questions in {path}")
    return questions


def ask(client: httpx.Client, api: str, question: str) -> dict:
    """POST one question and return the AskResponse as a dict (see api/app/schemas.py)."""
    response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question})
    response.raise_for_status()
    return response.json()


def _norm(section: str) -> str:
    """Compare headings, not typography: case, curly quotes, whitespace and trailing
    punctuation differ between a PDF's text layer and the golden set."""
    section = section.replace("’", "'").replace("‘", "'")
    return " ".join(section.lower().split()).rstrip(" .:")


def _key(passage: dict) -> tuple[str, str]:
    return passage["source"], _norm(passage["section"])


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Fraction of the relevant (source, section) pairs found in the top k retrieved.
    Return None when the question has no relevant passages (must-abstain questions)."""
    wanted = {_key(r) for r in relevant}
    if not wanted:
        return None
    found = {_key(r) for r in retrieved[:k]}
    return len(wanted & found) / len(wanted)


def _valid_citations(response: dict) -> tuple[int, int]:
    """(citations matching a retrieved passage on source, section and page, citations)."""
    citations = response.get("citations") or []
    retrieved = {(*_key(r), r.get("page")) for r in response.get("retrieved") or []}
    return sum((*_key(c), c.get("page")) in retrieved for c in citations), len(citations)


def citation_validity(response: dict) -> float | None:
    """Fraction of the response's citations that match a passage in response['retrieved'].
    Return None when there are no citations."""
    valid, total = _valid_citations(response)
    return valid / total if total else None


def _mean(values: list[float | None]) -> float | None:
    scored = [v for v in values if v is not None]
    return round(sum(scored) / len(scored), 4) if scored else None


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus
    recall@5 broken down by question type. This dict becomes results.json."""
    per_question = []
    cited = valid = 0
    for row in rows:
        response = row["response"]
        ok, total = _valid_citations(response)
        valid, cited = valid + ok, cited + total
        per_question.append({
            "id": row["id"], "type": row["type"], "must_abstain": row["must_abstain"],
            "recall@3": recall_at_k(row["relevant"], response.get("retrieved") or [], 3),
            "recall@5": recall_at_k(row["relevant"], response.get("retrieved") or [], 5),
            "citation_validity": ok / total if total else None,
            "answered_from_context": bool(response.get("answered_from_context")),
            "cached": bool(response.get("cached", False)),
            "seconds": row.get("seconds"),
        })
    abstain = [q for q in per_question if q["must_abstain"]]
    by_type: dict[str, dict] = {}
    for kind in sorted({q["type"] for q in per_question}):
        group = [q for q in per_question if q["type"] == kind]
        by_type[kind] = {"questions": len(group),
                         "recall@3": _mean([q["recall@3"] for q in group]),
                         "recall@5": _mean([q["recall@5"] for q in group])}
    return {
        "recall@3": _mean([q["recall@3"] for q in per_question]),
        "recall@5": _mean([q["recall@5"] for q in per_question]),
        # Pooled over every citation, so one answer with many citations weighs more.
        "citation_validity": round(valid / cited, 4) if cited else None,
        "citations": cited,
        "abstention_correctness": round(
            sum(not q["answered_from_context"] for q in abstain) / len(abstain), 4)
        if abstain else None,
        "by_type": by_type,
        "per_question": per_question,
    }


def gate(results: dict, baseline: dict | None) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass."""
    failures = []
    recall5 = results.get("recall@5")
    if baseline and baseline.get("recall@5") is not None:
        floor = baseline["recall@5"] - MAX_RECALL5_DROP
        if recall5 is None or recall5 < floor - 1e-9:
            failures.append(f"recall@5 {recall5} is more than {MAX_RECALL5_DROP:.0%} below "
                            f"the baseline {baseline['recall@5']}")
    answered = [q["id"] for q in results.get("per_question", [])
                if q["must_abstain"] and q["answered_from_context"]]
    abstention = results.get("abstention_correctness")
    if abstention is not None and abstention < REQUIRED_ABSTENTION:
        failures.append(f"must-abstain questions answered from context: {', '.join(answered)}")
    validity = results.get("citation_validity")
    if validity is None:
        failures.append("no citations to score: citation validity cannot be checked")
    elif validity < MIN_CITATION_VALIDITY:
        failures.append(f"citation validity {validity:.1%} is below "
                        f"{MIN_CITATION_VALIDITY:.0%}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAHBAR against a golden set.")
    parser.add_argument("--api", required=True, help="base URL, e.g. http://192.168.49.2")
    parser.add_argument("--host", help="Host header, when your Ingress rule names a host")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write these results as the new baseline")
    args = parser.parse_args()

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=120.0, headers=headers) as client:
        for q in questions:
            started = time.perf_counter()
            response = ask(client, args.api, q["question"])
            rows.append({
                "id": q["id"], "type": q.get("type", "ordinary"),
                "must_abstain": bool(q.get("must_abstain", False)),
                "relevant": q.get("relevant") or [],
                "expect": q.get("expect"),
                "response": response,
                "seconds": round(time.perf_counter() - started, 2),
            })
            print(f"  {q['id']:<5} {rows[-1]['seconds']:>6.2f}s  {q['question'][:60]}")

    try:
        results = summarise(rows)
        baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
        failures = gate(results, baseline)
    except NotImplementedError as exc:
        print(f"\nnot implemented yet: {exc}")
        return 2

    results["golden"] = str(args.golden)
    results["questions"] = len(rows)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults written to {args.out}")
    if args.update_baseline:
        args.baseline.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"baseline updated: {args.baseline}")

    if failures:
        print("\nGATE FAILED")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("\ngate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
