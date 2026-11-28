"""Query coverage (RAGOps E2, E4; paper 4.2.7): do the tests still match real usage?

    python eval/query_coverage.py [--live eval/live_queries.jsonl] [--golden eval/golden.jsonl]
                            [--threshold 0.80] [--min-share 0.85] [--label before]

For every live query, find the most similar golden question (cosine of their embeddings,
with the pinned EMBED_MODEL through Ollama). A query is covered when that similarity
reaches --threshold. The run fails (exit 1) when fewer than --min-share of the live
queries are covered: the paper flags a gap when under 85 % reach a score. Uncovered
queries are listed and grouped by their topic, the input for E4 (new golden questions).
Both values can come from the environment (COVERAGE_THRESHOLD, COVERAGE_MIN_SHARE), so a
ConfigMap can set them (decision R6). The result goes to eval/results/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "api"))
sys.path.insert(0, str(HERE))

from ragops_metrics import cosine  # noqa: E402


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def nearest(live: list[list[float]], golden: list[list[float]]) -> list[tuple[int, float]]:
    """For each live vector, (index of the most similar golden vector, its cosine)."""
    out = []
    for v in live:
        scores = [cosine(v, g) for g in golden]
        best = max(range(len(scores)), key=scores.__getitem__)
        out.append((best, scores[best]))
    return out


def report(live: list[dict], golden: list[dict], matches: list[tuple[int, float]],
           threshold: float, min_share: float) -> dict:
    rows, uncovered = [], {}
    for q, (g, score) in zip(live, matches):
        covered = score >= threshold
        rows.append({"id": q["id"], "query": q["query"], "topic": q.get("topic"),
                     "nearest_golden": golden[g]["id"], "nearest_question": golden[g]["question"],
                     "similarity": round(score, 4), "covered": covered})
        if not covered:
            uncovered.setdefault(q.get("topic") or "untagged", []).append(q["query"])
    share = sum(r["covered"] for r in rows) / len(rows) if rows else 0.0
    return {"threshold": threshold, "min_share": min_share, "live_queries": len(rows),
            "golden_questions": len(golden), "covered": sum(r["covered"] for r in rows),
            "coverage": round(share, 4), "passed": share >= min_share,
            "uncovered_by_topic": dict(sorted(uncovered.items(),
                                              key=lambda kv: (-len(kv[1]), kv[0]))),
            "queries": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAGOps E2/E4 query coverage check.")
    parser.add_argument("--live", type=Path, default=HERE / "live_queries.jsonl")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.jsonl")
    parser.add_argument("--threshold", type=float,
                        default=float(os.environ.get("COVERAGE_THRESHOLD", 0.80)))
    parser.add_argument("--min-share", type=float,
                        default=float(os.environ.get("COVERAGE_MIN_SHARE", 0.85)))
    parser.add_argument("--label", default="coverage")
    parser.add_argument("--out-dir", type=Path, default=HERE / "results")
    args = parser.parse_args(argv)

    from app.config import get_settings
    from app.providers.llm.embed import OllamaEmbedder

    settings = get_settings()
    embedder = OllamaEmbedder(settings)
    live, golden = _lines(args.live), _lines(args.golden)
    live_vectors = [embedder.embed(q["query"]) for q in live]
    golden_vectors = [embedder.embed(q["question"]) for q in golden]
    result = report(live, golden, nearest(live_vectors, golden_vectors),
                    args.threshold, args.min_share)
    result["embed_model"] = settings.embed_model

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{stamp}-{args.label}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"coverage: {result['covered']} of {result['live_queries']} live queries "
          f"({result['coverage']:.0%}) have a golden question with cosine >= "
          f"{args.threshold} (need {args.min_share:.0%})")
    for topic, queries in result["uncovered_by_topic"].items():
        print(f"  uncovered topic '{topic}' ({len(queries)}): " + "; ".join(queries))
    print(f"results written to {out}")
    print("PASS" if result["passed"] else "FAIL: coverage below the threshold")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
