"""D3: summarise the trace log over a time window.

    python -m app.tools.trace_summary [--since 2026-11-28T10:00] [--until ...] [--dir DIR]
    kubectl logs -n rahbar -l app=api --tail=-1 | python scripts/trace_summary.py --logs -
    python scripts/trace_summary.py --dir traces --json eval/results/d3-summary.json

Reports, for the traces whose timestamp is in [since, until):
    queries, outcomes, abstention rate, cache hit rate (hits / (hits + misses)),
    top-1 retrieval similarity distribution, p50 and p95 latency per stage,
    injection attempts flagged (by source), fallbacks, and the collection and embedding
    model each query used.
Times are UTC ISO 8601; a prefix such as 2026-11-28 or 2026-11-28T10 is enough.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .traces import load

STAGES = ("cache", "embed", "retrieve", "generate", "summary", "total")
BUCKETS = (0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0)


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile, the definition eval/ragops_metrics.py uses."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


def in_window(record: dict[str, Any], since: str | None, until: str | None) -> bool:
    ts = str(record.get("timestamp", ""))
    return (since is None or ts >= since) and (until is None or ts < until)


def summarise(records: list[dict[str, Any]], since: str | None = None,
              until: str | None = None) -> dict[str, Any]:
    rows = [r for r in records if in_window(r, since, until)]
    outcomes = Counter(str(r.get("outcome")) for r in rows)
    lookups = Counter(r.get("cache", {}).get("lookup") for r in rows)
    top1 = [max(c["score"] for c in r["retrieval"]["chunks"]) for r in rows
            if r.get("retrieval", {}).get("chunks") and not r["retrieval"]["chunks"][0]
            .get("from_cache")]
    flags = [g for r in rows for g in r.get("guardrails", []) if g.get("name") == "retrieval_rail"]
    histogram: dict[str, int] = {}
    low = 0.0
    for high in BUCKETS:
        histogram[f"{low:.2f}-{high:.2f}"] = sum(low <= s < high or (high == 1.0 and s == 1.0)
                                                 for s in top1)
        low = high
    hits, misses = lookups.get("hit", 0), lookups.get("miss", 0)
    n = len(rows)
    return {
        "window": {"since": since, "until": until,
                   "first": min((r["timestamp"] for r in rows), default=None),
                   "last": max((r["timestamp"] for r in rows), default=None)},
        "queries": n,
        "outcomes": dict(sorted(outcomes.items())),
        "abstention_rate": round(outcomes.get("abstained", 0) / n, 4) if n else None,
        "decline_rate": round(outcomes.get("declined", 0) / n, 4) if n else None,
        "fallback_rate": round(outcomes.get("fallback", 0) / n, 4) if n else None,
        "cache": {"hit": hits, "miss": misses, "skipped": lookups.get("skipped", 0),
                  "hit_rate": round(hits / (hits + misses), 4) if hits + misses else None},
        "top1_similarity": {
            "n": len(top1), "min": min(top1, default=None),
            "p25": percentile(top1, 25), "p50": percentile(top1, 50),
            "p75": percentile(top1, 75), "max": max(top1, default=None),
            "mean": round(sum(top1) / len(top1), 4) if top1 else None,
            "histogram": histogram},
        "latency_ms": {stage: {"n": len(v := [r["latency_ms"][stage] for r in rows
                                              if stage in r.get("latency_ms", {})]),
                               "p50": percentile(v, 50), "p95": percentile(v, 95)}
                       for stage in STAGES},
        "injections_flagged": {
            "total": len(flags),
            "by_source": dict(Counter(str(g.get("source")) for g in flags)),
            "queries_with_a_flag": sum(any(g.get("name") == "retrieval_rail"
                                           for g in r.get("guardrails", [])) for r in rows)},
        "by_collection": dict(Counter(f"{r.get('collection')} / {r['embedding']['model']}"
                                      for r in rows)),
    }


def render(s: dict[str, Any]) -> str:
    def f(v: Any) -> str:
        return "-" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v)

    w, t1, c, inj = s["window"], s["top1_similarity"], s["cache"], s["injections_flagged"]
    out = [f"trace summary  since {w['since'] or '-'}  until {w['until'] or '-'}  "
           f"(first {w['first']}, last {w['last']})",
           f"queries {s['queries']}   outcomes {json.dumps(s['outcomes'])}",
           f"abstention rate {f(s['abstention_rate'])}   decline rate {f(s['decline_rate'])}"
           f"   fallback rate {f(s['fallback_rate'])}",
           f"cache hit rate {f(c['hit_rate'])}  (hit {c['hit']}, miss {c['miss']}, "
           f"skipped {c['skipped']})",
           f"injection attempts flagged {inj['total']} {json.dumps(inj['by_source'])} in "
           f"{inj['queries_with_a_flag']} queries",
           f"collection / embedding model: {json.dumps(s['by_collection'])}",
           "",
           f"top-1 similarity  n {t1['n']}  min {f(t1['min'])}  p25 {f(t1['p25'])}  "
           f"p50 {f(t1['p50'])}  p75 {f(t1['p75'])}  max {f(t1['max'])}  mean {f(t1['mean'])}"]
    peak = max(t1["histogram"].values(), default=0) or 1
    out += [f"  {bucket}  {n:>4}  {'#' * round(30 * n / peak)}"
            for bucket, n in t1["histogram"].items()]
    out += ["", "| stage | n | p50 ms | p95 ms |", "| --- | --- | --- | --- |"]
    out += [f"| {stage} | {v['n']} | {f(v['p50'])} | {f(v['p95'])} |"
            for stage, v in s["latency_ms"].items()]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trace_summary", description=__doc__.splitlines()[0])
    parser.add_argument("--since", help="UTC ISO time, inclusive")
    parser.add_argument("--until", help="UTC ISO time, exclusive")
    parser.add_argument("--dir", help="trace directory (default: TRACE_DIR, else ./traces)")
    parser.add_argument("--logs", help="read `kubectl logs` output from this file, or -")
    parser.add_argument("--json", type=Path, help="also write the summary here as JSON")
    args = parser.parse_args(argv)
    summary = summarise(list(load(args.dir, args.logs)), args.since, args.until)
    print(render(summary))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nwritten to {args.json}")
    return 0 if summary["queries"] else 1


if __name__ == "__main__":
    sys.exit(main())
