"""RAGOps C2: the release gate passes a candidate within every threshold, fails one that
breaks any, never passes on a bad config, and reads its thresholds from a file, so a
ConfigMap edit changes the decision without a rebuild (F2)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gate  # noqa: E402

BASELINE = {"label": "baseline", "component": {"recall@5": 0.6875},
            "end_to_end": {"faithfulness": 0.7143, "abstention_correctness": 1.0,
                           "citation_validity": 1.0, "latency_p50_s": 2.43,
                           "latency_p95_s": 6.69}}


def _candidate(**changes: Any) -> dict[str, Any]:
    out = copy.deepcopy(BASELINE)
    for key, v in changes.items():
        level = "component" if key == "recall@5" else "end_to_end"
        out[level][key] = v
    return out


def _run(tmp_path: Path, candidate: dict, config: Path | None = None) -> tuple[int, dict]:
    b, c, out = tmp_path / "b.json", tmp_path / "c.json", tmp_path / "gate.json"
    b.write_text(json.dumps(BASELINE))
    c.write_text(json.dumps(candidate))
    args = [str(b), str(c), "--out", str(out)] + (["--config", str(config)] if config else [])
    code = gate.main(args)
    return code, json.loads(out.read_text()) if out.exists() else {}


def test_a_candidate_within_every_threshold_passes(tmp_path: Path) -> None:
    code, result = _run(tmp_path, _candidate(**{"latency_p95_s": 12.54, "faithfulness": 0.7333}))
    assert code == 0 and result["decision"] == "pass" and result["failed"] == []


@pytest.mark.parametrize("change,failed", [
    ({"recall@5": 0.5938}, "recall_at_5 max_drop"),           # all-minilm, -9.4 points
    ({"recall@5": 0.6670}, "recall_at_5 max_drop"),           # 2.05 points
    ({"faithfulness": 0.62}, "faithfulness min"),
    ({"latency_p95_s": 32.47}, "latency_p95_s max"),
    ({"latency_p50_s": 3.9}, "latency_p50_s max_ratio"),
    ({"abstention_correctness": 0.9167}, "abstention_correctness not_below_baseline"),
    ({"citation_validity": 0.9}, "citation_validity min"),
    ({"faithfulness": None}, "faithfulness min"),            # nothing judged is no pass
])
def test_breaking_any_rule_fails_the_gate(tmp_path: Path, change: dict, failed: str) -> None:
    code, result = _run(tmp_path, _candidate(**change))
    assert code == 1 and result["decision"] == "fail" and failed in result["failed"]


def test_exactly_two_points_is_still_a_pass(tmp_path: Path) -> None:
    assert _run(tmp_path, _candidate(**{"recall@5": 0.6675}))[0] == 0


def test_editing_the_threshold_file_changes_the_decision(tmp_path: Path) -> None:
    minilm = _candidate(**{"recall@5": 0.5938})
    rules = yaml.safe_load((ROOT / "config" / "gate.yaml").read_text())
    assert _run(tmp_path, minilm)[0] == 1
    rules["gate"]["recall_at_5"]["max_drop"] = 0.10
    edited = tmp_path / "gate.yaml"
    edited.write_text(yaml.safe_dump(rules))
    assert _run(tmp_path, minilm, edited)[0] == 0


@pytest.mark.parametrize("body", ["gate:\n  recall_at_50:\n    max_drop: 0.02\n",
                                  "gate:\n  recall_at_5:\n    max_dorp: 0.02\n",
                                  "gate: {}\n", "not: [valid"])
def test_a_bad_config_is_an_error_never_a_pass(tmp_path: Path, body: str) -> None:
    config = tmp_path / "bad.yaml"
    config.write_text(body)
    assert _run(tmp_path, _candidate(), config)[0] == 2


def test_a_file_that_is_not_a_suite_result_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "b.json").write_text(json.dumps(BASELINE))
    (tmp_path / "c.json").write_text("{}")
    assert gate.main([str(tmp_path / "b.json"), str(tmp_path / "c.json")]) == 2


def test_the_configmap_carries_the_same_gate_as_the_config_file() -> None:
    """config/gate.yaml (local runs) and the ragops-gate ConfigMap (the cluster) must not
    drift apart, or the cluster would gate on numbers nobody justified."""
    configmap = yaml.safe_load((ROOT / "k8s" / "base" / "ragops-gate.yaml").read_text())
    assert configmap["metadata"]["name"] == "ragops-gate"
    in_cluster = yaml.safe_load(configmap["data"]["gate.yaml"])
    assert in_cluster == yaml.safe_load((ROOT / "config" / "gate.yaml").read_text())
