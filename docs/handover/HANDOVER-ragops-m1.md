# Handover: Member 1's RAGOps work, for Member 2

Member 1's parts (A, B, C1, E) are merged into `dev` (PRs #33, #34, #35). This file is what
Member 2 needs to build C2, C3, D and F on top of them, plus the uniqueness check. Plan:
docs/planning/ragops-implementation-plan.md. Decisions R1-R13 and R10b:
docs/decisions/DECISIONS.md. Measured numbers: eval/results/final-44-summary.md.

## Read first: two things that changed since the plan

1. **The passing candidate is top_k 6, not chunking 200/40 (R10b).** Every chunking change lost
   more than 2 points of recall@5. The plan's P4 and P5 still say 200/40; follow R10b. all-minilm
   stays the failing candidate and the bad release.
2. **The commit split (R3).** Every RAGOps commit on `dev` so far is Member 1's. R3 needs each
   member at 40 % or more of `git shortlog -sn`. Commit C2, D and F in small steps.

## Status by part

| Part | Item | Owner | Status |
| --- | --- | --- | --- |
| A1 | quality, completeness, recency checks, quarantine, report per run | M1 | done |
| A1 | uniqueness check (exact and near duplicates) | **M2 (swap)** | slot ready, see below |
| A2 | data lake, incremental sync, restore, orphan pruning; Batch B | M1 | done |
| B | golden set (44), suite on three levels, judge agreement, two seeded runs | M1 + both | done |
| C1 | baseline against k6, c200, o40, minilm | M1 | done (locally) |
| C2 | `config/gate.yaml`, `ragops-gate` ConfigMap, `scripts/gate.py` | **M2** | open |
| C3 / F3 | `api-candidate`, rolling update, `rollout undo` | **M2** | open |
| D1-D4 | trace record, trace tool, metrics and summary, guardrail logging | **M2** | open |
| D5 | root cause from a trace | M1 writes, M2 reviews | waits on D1 |
| E1-E4 | live log, coverage 68 % to 88 %, drift, gap closed | M1 | done (locally) |
| F1, F2, F4, F5 | PVCs, Jobs and CronJob, traces on the volume, measured resources | **M2** | open |
| F2 | `k8s/eval-job.yaml` | **M1 (swap)** | waits on F1's PVC and the eval image |
| F | `k8s/README.md` fresh-cluster order | **M2** | open |
| G | report: M1 Parts A, B, C1, E and Q4 a, b, d; M2 Parts C2, D, F and Q4 c, e, f | both | open |

## Interfaces you plug into

### Uniqueness check (A1, your swap task)

- `indexer/pipeline/verify.py`: return `Check("uniqueness", passed, reason)`; `passed=None`
  means "not run". `decide()` already quarantines a document whose uniqueness check fails.
- Replace `uniqueness_not_run()` in the `checks = [...]` list in `indexer/pipeline/run.py`.
- Embeddings: `pipeline.embed.embed(texts, settings, client=None)` returns one vector per text
  with the pinned `EMBED_MODEL`. Compare against the documents already in `raw/` and against the
  others in the same batch.
- Test cases in Batch B (`corpus/batch_b/README.md` has the expected outcome of every file):
  b02 is an exact copy of b01, b04 an exact copy of b03, b05 a near duplicate of b03. Today all
  three are indexed. Put the threshold for "near" in the `ragops-gate` ConfigMap, with the
  similarities it was chosen from.
- Indexer tests use an autouse isolated data lake (`indexer/tests/conftest.py`); copy the
  pattern of `test_verify.py`.

### Ingestion Job (F1, F2)

- Same image and entry point as A02: `python -m pipeline.run`. Today `k8s/base/indexer.yaml`
  (Job `indexer`, CronJob `reindex`) downloads into an `emptyDir` at `/corpus`. Replace that with
  the `ragops-data` PVC (R4).
- Environment: `DATA_LAKE_DIR` (mount the PVC here), `CORPUS_DIR=$DATA_LAKE_DIR/raw`,
  `VERIFY_MIN_WORDS` (20), `VERIFY_MAX_GARBLED` (0.30), plus A02's `CHROMA_COLLECTION`,
  `CHUNK_SIZE`, `CHUNK_OVERLAP`, `EMBED_MODEL`.
- Command: `python corpus/fetch.py --out $DATA_LAKE_DIR/raw`, then `fetch.py --verify --out ...`,
  then `python -m pipeline.run`.
- Lake layout: `catalog.json`, `incoming/`, `raw/`, `archive/<doc_id>/<version>/`,
  `quarantine/` (with `<file>.reason.json`), `reports/verify-<run>.json` and
  `reports/ingest-<run>.json`.
- Operations in the same image: `python -m pipeline.ops counts | status | restore <doc_id>
  <version>`.
- Unseen batch for the demo: `corpus/batch_b/` is not in the image. Copy it into
  `$DATA_LAKE_DIR/incoming/` with `kubectl cp` through a pod that mounts the PVC; the next run
  moves it to `raw/`.

### Candidate collections (C1, F3; R9: built by the ingestion Job only)

| Collection | Settings that differ from the baseline | Role |
| --- | --- | --- |
| `rahbar-base` | none: 150/30, nomic-embed-text, top_k 5 | baseline, the live api |
| `rahbar-k6` | the api's `TOP_K=6` (same chunks as the baseline) | the passing candidate |
| `rahbar-minilm` | `EMBED_MODEL=all-minilm` in the Job and the api | the failing candidate and the bad release |
| `rahbar-c200`, `rahbar-o40` | `CHUNK_SIZE=200, CHUNK_OVERLAP=40`; `CHUNK_OVERLAP=40` | measured, fail recall |

- The api reads `CHROMA_COLLECTION`, `EMBED_MODEL` and `TOP_K`, so a candidate Deployment is the
  same image with those values changed.
- Build every C1 collection **before** Batch B goes into `incoming/`. Each run's intake moves
  `incoming/` into `raw/`, so a later candidate build would include Batch B and stop being
  comparable.
- Every indexer run invalidates the live cache as its last step, including a candidate build.
  That is expected.

### The suite and the gate (C2, F2)

- Run: `python eval/suite.py --api <url> --collection <name> --label <label> [--runs 2]
  [--out-dir <dir>]`. The output is `<out-dir>/<UTC stamp>-<label>.json`; point `--out-dir` at
  the `ragops-results` PVC.
- The suite exits 0 on every completed run. **Pass or fail is your gate's decision**:
  `scripts/gate.py baseline.json candidate.json` exits 1 on a failure, and the eval Job runs
  the gate after the suite so the Job itself fails.
- Keys the gate reads: `component["recall@5"]`, `end_to_end["faithfulness"]`,
  `end_to_end["latency_p50_s"]`, `end_to_end["latency_p95_s"]`,
  `end_to_end["abstention_correctness"]`, `end_to_end["citation_validity"]`. Also there:
  `component["mrr"]`, `component["ndcg@5"]`, `component["noise_test"]`, and, with `--runs 2`,
  `stochasticity["difference"]`.
- The suite talks to the api over HTTP and also to Chroma and Ollama directly, with the api's
  variables: `CHROMA_HOST`, `CHROMA_PORT`, `OLLAMA_URL`, `EMBED_MODEL`, `TOP_K`,
  `EMBED_TIMEOUT_SECONDS` (use 60).
- **Eval image:** the suite imports the api package. The api image is built from `api/` as its
  context and has no `eval/`. Build the eval image from the repo root with `api/app` and `eval/`
  in it, or extend the api Dockerfile. Decide this, then tell Member 1, who writes
  `k8s/eval-job.yaml`.
- Coverage: `python eval/query_coverage.py --label <label> [--out-dir <dir>]` exits 1 below the
  minimum share. `COVERAGE_THRESHOLD` (0.65, measured) and `COVERAGE_MIN_SHARE` (0.85) go into
  the `ragops-gate` ConfigMap (R6).

### Measured values for the gate thresholds (44 questions, local stack)

| Run | Collection | recall@5 | faithfulness | p50 (s) | p95 (s) | abstention |
| --- | --- | --- | --- | --- | --- | --- |
| baseline-44 | rahbar-base | 0.688 | 0.714 | 2.43 | 6.69 | 1.00 |
| k6-44-isolated | rahbar-k6 | 0.688 | 0.733 | 2.44 | 12.54 | 1.00 |
| minilm-44 | rahbar-minilm | 0.594 | 0.750 | 0.06 | 3.37 | 1.00 |
| c200-44 | rahbar-c200 | 0.641 | 0.733 | 2.38 | 20.56 | 1.00 |
| o40-44 | rahbar-o40 | 0.625 | 0.812 | 2.24 | 5.37 | 1.00 |

- With the rule "recall@5 drops by no more than 2 points", k6 passes and minilm fails.
- Faithfulness X: the two seeded baseline runs and the judge's 75 % agreement with the hand
  labels are the evidence. Don't set X above what the baseline itself reaches.
- Latency Y: **do not gate on local p95.** It swings from 3 s to 32 s on the same code because
  the laptop's Ollama prompt-cache restore stalls (up to 7.2 s at a time in its log). Gate on p50,
  or measure p95 as a cluster Job and justify Y from that.
- minilm's p50 of 0.06 s is declines, not speed: its similarities fall under the relevance
  floor of 0.65, which was measured for nomic-embed-text. Its recall drop is the signal, not its
  latency.
- All these numbers are local (Chroma in Docker, Ollama on the host GPU). The brief wants the
  report's numbers from the cluster: re-run them as Jobs once F2 works.

### Trace record (D1-D4)

- Hook point: `api/app/services/answer.py`, `answer_question()`. Its module docstring lists the
  query steps in order, and each step holds values a trace needs: retrieved passages with
  scores, the filter from `asks_about_older_version`, the prompt from `build_prompt`, and the
  generation result with attempts and fallback.
- Retrieved chunk metadata already has `doc_id`, `doc_version`, `superseded` and the content
  hash. Every `rahbar-*` collection stores its embedding model and dimension in its metadata.
- Metrics live in `api/app/routes/metrics.py` (abstentions, fallbacks, cache lookups, latency
  histograms). Add the top-1 similarity histogram and the injection-flagged counter there, with
  bounded labels only.
- D4 test document: Batch B's b09 (`b09-it-acceptable-use.md`) has "Ignore all previous
  instructions..." in section 3. It passes verification on purpose; the guardrail has to catch it
  at query time.
- Rules carried from A02: no secrets in a trace; the full prompt goes to the volume, never to INFO
  logs (ADR 0004); the poisoned-chunk test stays.
- **D5 depends on this.** Member 1 needs one trace with scores and versions to write the root
  cause. Send a trace id when D1 runs on the cluster.

### Controlled release (C3, F3)

- `api-candidate`: a second Deployment and Service, same image, its own `CHROMA_COLLECTION`,
  `EMBED_MODEL` and `TOP_K`, and its own NetworkPolicy allow rules copied from the api's.
- Bad release with `rollout undo`: change the live Deployment's environment with
  `kubectl set env deployment/api ...`, not the shared `rahbar-config` ConfigMap. A ConfigMap
  edit does not start a rollout, so there is no revision to undo, and the indexer reads the same
  ConfigMap.
- The embedding pin (A02 §4.4): an api with `EMBED_MODEL=all-minilm` must point at
  `rahbar-minilm`, or it stays not-ready by design. The trace after the undo must show the
  previous collection and embedding model.

## Local stack Member 1 measured on

- Docker network `rahbar`: `chromadb/chroma:1.0.12` on 127.0.0.1:8001 (volume
  `ragops-chroma-data`), `redis:7.4.2` on 6379.
- Ollama 0.40.19 on the host GPU with llama3.2:3b, nomic-embed-text and all-minilm.
- The indexer image is `rahbar-indexer:ragops` (it has tesseract); the api runs from `.venv`.

## Traps already hit (docs/failure-log.md has the details)

- Use `127.0.0.1`, not `localhost`, for Ollama on the laptop: `localhost` costs about 2 s per
  request because IPv6 is tried first. On the cluster use `host.minikube.internal`.
- Set `EMBED_TIMEOUT_SECONDS=60`: the first embedding after a model load can take longer than
  the default.
- Ollama can run on the CPU only after a reinstall. Check that `ollama ps` shows `100% GPU`
  before measuring anything.
- Several api processes against one Ollama inflate p95 (k6: 32 s with six apis running, 12.5 s
  alone). Run measurement Jobs one at a time.
- `*.log` is gitignored; commit evidence as `.txt`.

## Closed (2026-11-28)

Member 2 delivered items 1-4 (docs/handover/HANDOVER-ragops-m2.md). Member 1 then:

- wrote `k8s/eval-job.yaml` (suite and gate, fails when the gate fails) and
  `k8s/coverage-job.yaml` (Part E, fails below 85 %), and ran both on a fresh minikube
  (eval/results/cluster-m1/);
- wrote D5 from trace `7087caa6dc4949aea29a80263a9e8fb2` (q13, a Part B answer) rather than
  the suggested `61e8b56d...`, because D5 asks for an answer from Part B;
- drafted docs/report/member1-sections.md (Parts A, B, C1, D5, E; Q4 a, b, d);
- recorded the fetch.py re-download as WONTFIX (DECISIONS R17).

## Member 1's review of Member 2's changes in Member 1's area

Post-merge review of PRs #37-#40 (uniqueness, trace and guardrail hooks, cache scope).
None of these is a deduction-ledger risk; each is a known limit with an upgrade path.

1. `indexer/pipeline/verify.py`, `Duplicates.check`: the exact-duplicate test runs before
   the "another version of the same doc_id is recency's case" skip. A new version whose
   extracted text is identical to the old one is quarantined as a duplicate instead of
   superseding it. WONTFIX: an unchanged republished document has nothing to supersede, and
   the reason file names the original.
2. `api/app/services/answer.py`: a question the retrieval rail flags (`check_question`) can
   still be cached; only flagged evidence blocks the cache. A grounded answer to an
   injection-style question (q19) is then served to near-identical questions. Low risk,
   because the answer passed citation validation; making a flagged question skip the cache
   like a follow-up is one condition in `safe`.
3. `api/app/providers/cache/__init__.py`, `config_scope`: the scope has the collection,
   model, top_k, floor, provider, temperature and guardrail action, but not `LLM_SEED` or a
   prompt-template version. A prompt change without an index run would serve old answers.
   Add a prompt-template hash to the scope if prompts change outside a release.
4. `indexer/pipeline/verify.py`, `Duplicates.save`: `signatures.json` is rewritten in place,
   like `catalog.json` (the single-writer WONTFIX in PR #33 applies to both).
