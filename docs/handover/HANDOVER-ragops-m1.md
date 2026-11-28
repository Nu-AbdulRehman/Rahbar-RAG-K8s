# Handover: Member 1's RAGOps work, for Member 2

Branches (stacked, merge in order): `ragops/a-data-management` → `ragops/b-test-suite` →
`ragops/e-coverage`. Plan: docs/planning/ragops-implementation-plan.md; decisions R1-R13 and
R10b in docs/decisions/DECISIONS.md.

## What exists, and what your parts plug into

**Ingestion with verification (Part A)**, the only Chroma writer (R9). Same image and entry
point as A02: `python -m pipeline.run`. New environment variables, all with defaults:

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATA_LAKE_DIR` | `/tmp/ragops` | the data lake root; mount the `ragops-data` PVC here (R4) |
| `CORPUS_DIR` | `/corpus` | raw documents; set it to `$DATA_LAKE_DIR/raw` with the PVC |
| `VERIFY_MIN_WORDS` | 20 | quality check |
| `VERIFY_MAX_GARBLED` | 0.30 | quality check |

Lake layout: `catalog.json`, `incoming/` (a new batch: the demo copies files here, the next
run's intake moves them to `raw/`), `raw/`, `archive/<doc_id>/<version>/`, `quarantine/`,
`reports/verify-<run>.json` and `reports/ingest-<run>.json`. The Job's command on the
cluster becomes `fetch.py --out $DATA_LAKE_DIR/raw`, `fetch.py --verify --out ...`, then
`python -m pipeline.run`. Other commands in the same image: `python -m pipeline.ops counts |
status | restore <doc_id> <version>`.

**Your uniqueness check (A1, your swap task):** `indexer/pipeline/verify.py` reports it as
`uniqueness_not_run()`. Replace that call in `indexer/pipeline/run.py` (the `checks = [...]`
list) with your check returning a `Check("uniqueness", passed, reason)`; `decide()` already
quarantines on a uniqueness failure. Batch B's b02 and b04 (exact) and b05 (near) are the
cases; corpus/batch_b/README.md has the expected outcomes.

**The suite (Part B)**, for your gate (C2) and the eval Job (F2):
`python eval/suite.py --api <url> --collection <name> --label <label> [--runs 2]` writes
`eval/results/<UTC stamp>-<label>.json`. Top-level keys your gate needs:
`component["recall@5"]`, `end_to_end["faithfulness"]`, `end_to_end["latency_p95_s"]`,
`end_to_end["abstention_correctness"]` (plus `citation_validity`, `mrr`, `ndcg@5`). It reads
Chroma and Ollama from the api's variables (`CHROMA_HOST`, `CHROMA_PORT`, `OLLAMA_URL`,
`EMBED_MODEL`, `TOP_K`, `EMBED_TIMEOUT_SECONDS`), so the eval Job image needs api/ and eval/
on the path, which the api image almost has (add eval/).

**Coverage (Part E):** `python eval/query_coverage.py --label <label>`, exit 1 below the
minimum share. `COVERAGE_THRESHOLD` (0.65, measured) and `COVERAGE_MIN_SHARE` (0.85) belong
in the `ragops-gate` ConfigMap (R6).

## Measured, for C2 and F3

On the final 44-question golden set (eval/results/final-44-summary.md, 2026-11-28):

| label | collection | recall@5 | faithfulness | p50 (s) | abstention | for |
| --- | --- | --- | --- | --- | --- | --- |
| baseline-44 | rahbar-base (150/30, nomic, pre-Batch-B) | 0.688 | 0.714 | 2.43 | 1.00 | the live api |
| k6-44 | rahbar-k6 (top_k 6) | 0.688 | 0.733 | 2.44 | 1.00 | the passing candidate (R10b) |
| minilm-44 | rahbar-minilm (all-minilm) | 0.594 | 0.750 | 0.06 | 1.00 | the failing candidate and the bad release |
| c200-44 | rahbar-c200 (200/40) | 0.641 | 0.733 | 2.38 | 1.00 | measured, fails recall |
| o40-44 | rahbar-o40 (150/40) | 0.625 | 0.812 | 2.24 | 1.00 | measured, fails recall |

The api reads `CHROMA_COLLECTION`, `EMBED_MODEL` and `TOP_K`, so each candidate Deployment
is the same image with those three values changed. Gate on the median latency or on cluster
numbers: local p95 swings from 3 s to 32 s on the same code (Ollama prompt-cache stalls, see
the summary). all-minilm's low latency is declines, because its similarities fall under the
nomic-calibrated relevance floor. All numbers were measured locally (Chroma in Docker, Ollama
on the host GPU); re-run them as Jobs on the cluster for the report.

## Done by the members

- 8 golden questions written by hand (q37-q44, 4 each), 8 synthetic ones reviewed by both.
- 8 faithfulness hand labels: judge agreement 6 of 8 (eval/results/faithfulness-agreement.txt).

## Still waiting on Member 2

- The uniqueness check, C2/C3, D and F.
- D5's root cause needs your trace record first.
