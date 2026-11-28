"""The RAGOps release gate (Part C2): compare a candidate's suite result with the
baseline's and exit 0 (release) or 1 (reject).

    python scripts/gate.py BASELINE.json CANDIDATE.json [--config config/gate.yaml]
                           [--out gate-result.json]

BASELINE and CANDIDATE are eval/suite.py result files. The thresholds come from
--config, else the GATE_CONFIG environment variable (the eval Job points it at the
ragops-gate ConfigMap mounted at /config/gate.yaml), else config/gate.yaml.

Exit codes: 0 every rule passed; 1 at least one rule failed; 2 the inputs or the config
are unusable (a missing file, an unknown metric or rule kind). A bad config never passes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
# metric name in gate.yaml -> where eval/suite.py writes it
METRICS = {
    "recall_at_5": ("component", "recall@5"),
    "recall_at_3": ("component", "recall@3"),
    "mrr": ("component", "mrr"),
    "ndcg_at_5": ("component", "ndcg@5"),
    "faithfulness": ("end_to_end", "faithfulness"),
    "abstention_correctness": ("end_to_end", "abstention_correctness"),
    "citation_validity": ("end_to_end", "citation_validity"),
    "latency_p50_s": ("end_to_end", "latency_p50_s"),
    "latency_p95_s": ("end_to_end", "latency_p95_s"),
}
KINDS = ("min", "max", "max_drop", "max_ratio", "not_below_baseline")
EPS = 1e-9


class GateError(Exception):
    """The gate cannot be applied: exit 2, never a pass."""


def value(result: dict[str, Any], metric: str) -> float | None:
    level, key = METRICS[metric]
    v = result.get(level, {}).get(key)
    return None if v is None else float(v)


def load_config(path: Path) -> dict[str, dict[str, Any]]:
    try:
        body = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GateError(f"cannot read gate config {path}: {exc}") from exc
    rules = (body or {}).get("gate")
    if not isinstance(rules, dict) or not rules:
        raise GateError(f"{path} has no 'gate:' rules")
    for metric, spec in rules.items():
        if metric not in METRICS:
            raise GateError(f"unknown metric {metric!r} in {path}; known: {sorted(METRICS)}")
        if not isinstance(spec, dict) or not spec:
            raise GateError(f"{metric}: no rule given")
        for kind in spec:
            if kind not in KINDS:
                raise GateError(f"{metric}: unknown rule {kind!r}; known: {KINDS}")
    return rules


def check(metric: str, kind: str, limit: Any, base: float | None,
          cand: float | None) -> tuple[bool, str]:
    """(passed, the rule in words with the numbers)."""
    if cand is None:
        return False, "candidate has no value"
    if kind in ("max_drop", "max_ratio", "not_below_baseline") and base is None:
        return False, "baseline has no value"
    if kind == "min":
        return cand >= float(limit) - EPS, f"{cand:.4g} >= {float(limit):.4g}"
    if kind == "max":
        return cand <= float(limit) + EPS, f"{cand:.4g} <= {float(limit):.4g}"
    assert base is not None
    if kind == "max_drop":
        drop = base - cand
        return drop <= float(limit) + EPS, f"drop {drop:+.4f} <= {float(limit):.4f}"
    if kind == "max_ratio":
        ratio = cand / base if base else float("inf")
        return ratio <= float(limit) + EPS, f"{cand:.4g} / {base:.4g} = {ratio:.3f} <= {limit}"
    if limit is not True:
        raise GateError(f"{metric}: not_below_baseline must be true")
    return cand >= base - EPS, f"{cand:.4g} >= baseline {base:.4g}"


def apply(baseline: dict[str, Any], candidate: dict[str, Any],
          rules: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for metric, spec in rules.items():
        base, cand = value(baseline, metric), value(candidate, metric)
        for kind, limit in spec.items():
            passed, detail = check(metric, kind, limit, base, cand)
            rows.append({"metric": metric, "rule": kind, "threshold": limit,
                         "baseline": base, "candidate": cand, "passed": passed,
                         "detail": detail})
    return {"decision": "pass" if all(r["passed"] for r in rows) else "fail",
            "failed": [f"{r['metric']} {r['rule']}" for r in rows if not r["passed"]],
            "rules": rows}


def render(outcome: dict[str, Any], baseline: dict[str, Any], candidate: dict[str, Any],
           config: Path) -> str:
    def f(v: Any) -> str:
        return "-" if v is None else f"{v:.4f}" if isinstance(v, float) else str(v)

    def name(r: dict[str, Any]) -> str:
        return (f"{r.get('label')} ({r.get('collection')}, {r.get('embed_model')}, "
                f"top_k {r.get('top_k')}, {r.get('timestamp')})")

    out = [f"release gate, config {config}",
           f"  baseline:  {name(baseline)}", f"  candidate: {name(candidate)}", "",
           f"{'metric':24} {'rule':20} {'baseline':>9} {'candidate':>9}  result  detail",
           "-" * 96]
    for r in outcome["rules"]:
        rule = f"{r['rule']} {r['threshold']}" if r["rule"] != "not_below_baseline" \
            else "not below baseline"
        out.append(f"{r['metric']:24} {rule:20} {f(r['baseline']):>9} {f(r['candidate']):>9}  "
                   f"{'PASS' if r['passed'] else 'FAIL':6}  {r['detail']}")
    out.append("")
    out.append("GATE PASS: release the candidate" if outcome["decision"] == "pass" else
               f"GATE FAIL: reject the candidate ({', '.join(outcome['failed'])})")
    return "\n".join(out)


def _read(path: Path) -> dict[str, Any]:
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GateError(f"cannot read result file {path}: {exc}") from exc
    if not isinstance(body, dict) or "component" not in body or "end_to_end" not in body:
        raise GateError(f"{path} is not an eval/suite.py result file")
    return body


def _shown(path: Path) -> Path:
    """The config path as a reader of the output expects it: relative to the repository
    when it is inside it (config/gate.yaml), as given otherwise (/config/gate.yaml)."""
    try:
        return path.resolve().relative_to(ROOT)
    except ValueError:
        return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the RAGOps release gate (C2).")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--config", type=Path,
                        default=Path(os.environ.get("GATE_CONFIG", ROOT / "config" / "gate.yaml")))
    parser.add_argument("--out", type=Path, help="write the decision here as JSON")
    args = parser.parse_args(argv)
    try:
        rules = load_config(args.config)
        baseline, candidate = _read(args.baseline), _read(args.candidate)
        outcome = apply(baseline, candidate, rules)
    except GateError as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return 2
    print(render(outcome, baseline, candidate, _shown(args.config)), flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "config": str(_shown(args.config)), "thresholds": rules,
            "baseline": str(args.baseline), "candidate": str(args.candidate),
            **outcome}, indent=2), encoding="utf-8")
    return 0 if outcome["decision"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
