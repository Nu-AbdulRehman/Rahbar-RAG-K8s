# RAGOps Implementation Plan (Assignment 03)

Nov 27, 2026 · the user

## Overview

Assignment 03 adds a "RAGOps layer" to the RAHBAR pipeline from Assignment 02: a data management lifecycle (verify, update the data lake, update the retrieval sources) beside the software lifecycle, tested at three levels, gated, traced, checked for drift, and run entirely on Kubernetes (`docs/planning/RAGOPS_problem_statement.pdf`, 185 marks, 2 members). The reference is the RAGOps paper (Xu et al., 2026): sections 3.2, 4.2, Tables 1 and 2, 5.1 and 6.2; Figure 3 is the map of the assignment.

**What "done" means.** A fresh minikube reaches a working pipeline by applying `k8s/` plus the commands in `k8s/README.md`. At the demo, both members can:
- run the evaluation as a Kubernetes Job;
- open a trace and rebuild its prompt;
- ingest an unseen batch of documents with the ingestion Job, watching verification quarantine the bad ones.

Every number in the report comes from our own runs, and every result file is committed under `eval/results/` and `traces/`.

**Hard constraints from the brief:**
- The demo runs on Kubernetes. Plain `docker run` or Compose scores 0.
- Commits must come from both members.
- No requirement may be changed.
- Both members can explain every part.

**Source of truth, highest first:** RAGOPS_problem_statement.pdf (cited as Part X.N) > the paper > this plan > CLAUDE.md / AGENTS.md (still binding: account split, no secrets, no push to main, tests that can fail, AI-USAGE logging).

## What Assignment 02 already gives us

| Brief item | Already in the repo | Gap to close |
| --- | --- | --- |
| A2 incremental update | `indexer/pipeline/store.py` upserts and prunes stale ids, so a deleted document leaves no chunks; the pin rebuilds on a model change | Unchanged documents are still re-embedded. Add a content hash per chunk and skip embedding when the hash already exists. Add archive, restore and per-document counts. |
| Superseded versions | `doc_version` and `superseded` metadata plus the retrieval filter | Archive folder on the data lake and a rollback command |
| A1 verification | `corpus/fetch.py --verify` (SHA-256 against MANIFEST), zero-chunk guard in `run.py` | Four checks (quality, completeness, recency, uniqueness), quarantine and a report per run |
| B component level | recall@3/@5, citation validity, abstention in `eval/run_eval.py` | MRR, nDCG@5, noise test, golden set migrated to `golden.jsonl` and grown to 25+ |
| B end to end | Abstention 100 %, citation validity 1.00 | Faithfulness (LLM judge plus 8 hand labels), latency p50/p95, a two-run stochasticity check |
| D observability | JSON logs with request_id, one log line per request (top_k, chunk ids, scores), `/metrics` with abstentions, cache and tokens | A full trace record (D1 field list), a trace volume, a trace tool, a windowed summary script, guardrail actions in the trace |
| F Kubernetes | Namespace, api Deployment + HPA, chroma StatefulSet, redis + PVC, indexer Job + CronJob, NetworkPolicy, requests and limits from `kubectl top` | Data lake PVC, eval Job, gate ConfigMap, candidate Deployment + Service + collection, results and trace volumes |
| Release gate | `run_eval.py` gate and e2e-eval in CI | A config-file gate with the brief's rules, pass and fail candidates |

## Global decisions

These become rows in `docs/decisions/DECISIONS.md` in the bootstrap phase.

| # | Decision | Rule it implies |
| --- | --- | --- |
| R1 | Build on RAHBAR (same repo, new branch prefix `ragops/`) | The A02 work stays intact on `main`; A03 work goes feature branch → dev → main as before |
| R2 | Member 1 = Nu-AbdulRehman, Member 2 = MTH99910 | Every commit, PR and review goes through the owner's account (CLAUDE.md §1.23); each reviews the other's PRs |
| R3 | **Balanced commits** | Assignment 02 ended at 67/33. Here each member owns about half the code (see Division). Each splits work into small commits, and neither drops below 40 % of `git shortlog -sn` |
| R4 | The data lake is a PVC (`ragops-data`) with `raw/`, `quarantine/`, `archive/`, `reports/` | Replaces the A02 emptyDir; it survives pod restarts (F1) |
| R5 | Results and traces live on a PVC (`ragops-results`) and are copied into `eval/results/` and `traces/` for commit | One `kubectl cp` script per run, so the committed files are the cluster's own output |
| R6 | All thresholds in one ConfigMap (`ragops-gate`) | Verification thresholds, coverage threshold and gate rules; changing one never needs a rebuild (F2) |
| R7 | Default LLM stays llama3.2:3b on host Ollama; the faithfulness judge is the same model, validated against 8 hand labels | Reported agreement rate (Part B) |
| R8 | Seeds are fixed (Ollama `seed`, temperature, Python `random`) and the suite runs twice | Part B stochasticity |
| R9 | The ingestion Job is the only writer to Chroma, for every collection including the candidate's | The candidate collection is built by the same Job template with a different `CHROMA_COLLECTION` (F3) |
| R10 | Part C change: chunking 200/40 is the passing candidate; the embedding model all-minilm (instead of nomic-embed-text) is the deliberately failing one | C1 compares both against the 150/30 nomic-embed-text baseline; F3 releases 200/40, and uses all-minilm as the bad release reversed with `rollout undo`, so the trace after the undo shows a different collection *and* embedding version |
| R11 | The faithfulness judge is llama3.2:3b on host Ollama | No key and no data leaves the laptop; agreement measured against 8 hand-labelled answers (Part B) |
| R12 | Namespace stays `rahbar` | A02's NetworkPolicy, ConfigMap, Ingress and ServiceAccounts carry over; new objects are added to `k8s/base` |
| R13 | Batch B is crafted from our own copies of corpus documents plus files we write | The planted problems are controlled and the files can be committed (`corpus/batch_b/`) |

## Division of work

Member 1 owns the data and evaluation lifecycle (Parts A, B, C1, E). Member 2 owns observability, the release gate and Kubernetes (Parts C2, C3, D, F). That is about the same amount of code each. The golden set, the report and the demo are shared.

| Part | Item | Member 1 (Nu-AbdulRehman) | Member 2 (MTH99910) |
| --- | --- | --- | --- |
| A | A1 four verification checks, quarantine, report | ● | |
| A | A2 hash-based incremental update, archive, restore, orphan proof | ● | |
| A | Batch B (10+ docs with planted problems) | ● | |
| B | Golden set to 25+ in `golden.jsonl` | ● writes 4 hand questions, reviews Member 2's synthetic ones | ● writes 4 hand questions, generates and labels synthetics |
| B | Module level (embedding pairs, time, determinism) | ● | |
| B | Component level (recall, MRR, nDCG, noise) | ● | |
| B | End-to-end (faithfulness judge, abstention, citations, latency) | ● | |
| B | Stochasticity (two seeded runs) and the one-command suite | ● | |
| C | C1 change experiment (baseline vs candidate) | ● | |
| C | C2 gate config and gate script | | ● |
| C | C3 rollout | | ● (with F3) |
| D | D1 trace record (all fields) | | ● |
| D | D2 trace tool, D3 metrics + summary script, D4 guardrail logging | | ● |
| D | D5 root cause from a trace | ● writes it (owns the answers) | ● reviews |
| E | E1 live query log, E2 coverage, E3 drift, E4 close the gap | ● | |
| F | F1 data lake PVC, F2 Jobs and gate ConfigMap, F3 candidate release, F4 trace volume, F5 measured resources | | ● |
| F | `k8s/README.md` fresh-cluster order | | ● |
| G | Report tables 1–3 | ● Parts A, B, C1, E | ● Parts C2, D, F |
| G | Report Q4 (a)–(f) | ● a, b, d | ● c, e, f |
| G | Contribution table and AI statement, screenshots | Both | Both |

**Swaps:** each member does one real task in the other's area.
- **Member 1 into the platform:** writes the eval Job manifest (`k8s/eval-job.yaml`), because it wraps the suite they built.
- **Member 2 into the data side:** builds the uniqueness check (A1 exact and near duplicates by embedding similarity), because it reuses the embedding client and the trace-side similarity code.

## Phases

### P0 · Bootstrap (both, half a day)
1. **Decisions and branches.** Add R1–R13 to DECISIONS.md; create `ragops/` feature branches from dev; log skills in AI-USAGE.md as before.
2. **Read the paper.** Each member writes a 5-line note on Figure 3's seven stages for the report's table 1.
3. **Rebuild the local stack.** Restore `.venv`, `make cluster`, apply A02's manifests, and confirm the A02 pipeline still answers through the Ingress. This is the baseline everything is measured against.

### P1 · Data management, Part A (Member 1)
1. **A1 verification stage** (`indexer/pipeline/verify.py`, between extract and chunk). For every document it records pass or fail, with a reason, for four checks:
   - **quality:** empty text, a garbled-text ratio, or failed extraction;
   - **completeness:** source, title, date or version and page count present, and the text not truncated (last-page text, EOF marker);
   - **recency:** a newer `doc_version` of the same document id exists;
   - **uniqueness:** exact duplicates by SHA-256, near duplicates by embedding cosine above a ConfigMap threshold.

   A failed document moves to `quarantine/` and is not indexed. Each run writes `reports/verify-<timestamp>.json` plus a printed table.
2. **A2 incremental update.**
   - Store a `content_hash` per chunk; embed only new or changed hashes, so an unchanged corpus re-run embeds 0 (counts printed).
   - A changed document replaces only its own chunks.
   - A deleted document leaves 0 chunks: count by `doc_id`.
   - A superseded version moves to `archive/` with `superseded: true`. A `restore <doc_id> <version>` command rolls it back.
3. **Batch B** (`corpus/batch_b/`, our own files, so they can be committed):
   - 10 or more documents, including 2 exact duplicates, 1 near duplicate, 1 truncated or corrupt file, 1 with missing metadata, 1 newer version of an existing document, and 1 with an injected instruction;
   - an expected-outcome table per file, so the verification report can be checked against it.
4. **Tests.** One unit test per check and per A2 rule, each shown to fail without the implementation.
- **Rules:** verification never deletes a source file, it only moves it. The ingestion Job stays the only Chroma writer.

### P2 · Observability, Part D (Member 2, in parallel with P1)
1. **D1 trace record** (`api/app/services/trace.py`). One JSON line per query with every D1 field:
   - identity and query: trace id, timestamp, query, rewritten query;
   - retrieval: embedding model and version, collection, chunk ids with document ids, versions and scores, filters, reranked order;
   - generation: prompt hash plus the full prompt (stored on the volume only), model and parameters, response, citations;
   - controls and timing: guardrail actions, latency per stage, cache hit or miss.

   Lines go to stdout and to `/traces/traces-<date>.jsonl` on the results PVC.
2. **D2 trace tool** (`scripts/trace_show.py <trace_id>`): prints the exact context and prompt that produced the answer.
3. **D3 metrics.** Add a top-1 similarity histogram and an injection-flagged counter to `/metrics`, beside the existing abstention, cache and latency metrics. `scripts/trace_summary.py --since/--until` summarises a time window.
4. **D4 guardrail logging.** The injection defence (delimiting, marker and citation checks) plus a simple retrieval rail that flags instruction-like text in a chunk write their action into the trace. Tested with Batch B's injected document.
- **Rules:** traces hold no secrets; the full prompt is on the volume, not in INFO logs (A02 ADR 0004 still applies).

### P3 · Offline test suite, Part B (Member 1; golden set shared)
1. **Golden set** (`eval/golden.jsonl`, migrated from golden.yaml):
   - at least 25 questions: 15 or more answerable (with ground-truth document and page), 5 or more unanswerable, 5 or more hard (paraphrased, multi-chunk, or from Batch B);
   - at least 8 written by hand (4 per member);
   - every question labelled human or synthetic, and at least 8 synthetic ones reviewed by hand (reviewer recorded).
2. **Module level.** 15 or more paraphrase pairs against 15 or more unrelated pairs: mean cosine for each and the gap; embedding time per chunk; determinism (embed twice, largest difference).
3. **Component level.** recall@3, recall@5, MRR and nDCG@5. Noise test: 3 or more irrelevant documents, or typo'd queries, with the change in each metric.
4. **End-to-end level.**
   - Faithfulness by the LLM judge, plus 8 answers labelled by hand and the agreement rate.
   - Abstention correctness, citation validity, and latency p50 and p95.
5. **Stochasticity.** Seeds fixed; the whole suite run twice; the difference per metric, with remaining variation explained.
6. **One command** (`python eval/suite.py --target <api-url> --collection <name>`): writes `eval/results/<timestamp>.json` plus a summary table.
- **Rules:** the golden set is written before the C1 experiment; no golden edit to pass a gate.

### P4 · Change experiment and gate, Part C (C1 Member 1, C2 Member 2)
1. **C1 one change** (R10). Index two candidate collections with the ingestion Job: `rahbar-c200` (chunk 200/40, nomic-embed-text) and `rahbar-minilm` (150/30, all-minilm). Run the suite on the baseline (`rahbar`, 150/30, nomic-embed-text) and on each candidate, and compare all three levels.
2. **C2 release gate** (`config/gate.yaml`, mirrored in the `ragops-gate` ConfigMap; `scripts/gate.py baseline.json candidate.json`, exit 0 or 1). Rules:
   - recall@5 drops by no more than 2 points;
   - faithfulness at least X;
   - p95 latency at most Y;
   - abstention no lower than the baseline.

   X and Y are justified from the baseline runs. Show one candidate that fails and one that passes.
3. **C3 roll-out.** Covered by F3.

### P5 · Kubernetes, Part F (Member 2; eval Job manifest is Member 1's swap)
1. **F1.** The api Deployment and Service and the chroma StatefulSet stay as they are. Add the `ragops-data` and `ragops-results` PVCs, mounted by the Jobs and, for traces, the api.
2. **F2 Jobs.**
   - Ingestion runs as a Job and a CronJob (verify → chunk → embed → store), still the only Chroma writer, reading from the data lake PVC.
   - The eval suite runs as a Job (`kubectl apply -f k8s/eval-job.yaml`), writes to the results volume, and exits non-zero when the gate fails.
   - The gate thresholds live in a ConfigMap. Edit a threshold, re-run the Job, and the outcome changes with no rebuild.
3. **F3 controlled release.**
   - The candidate runs as a second Deployment (`api-candidate`) with its own Service and collection, and the eval Job runs against it.
   - A gate pass leads to a rolling update of the live Deployment (`maxUnavailable: 0`) watched with `kubectl rollout status`.
   - A gate-stopped candidate (all-minilm) is shown never rolled out.
   - The passing candidate (200/40) is released through the rolling update.
   - A bad release (all-minilm pushed to the live Deployment on purpose, bypassing the gate) is reversed with `kubectl rollout undo`, and a new trace shows the previous collection and embedding version.
4. **F4.** Traces go to stdout (visible with `kubectl logs`) and to the volume; `/metrics` is reachable with `kubectl port-forward`.
5. **F5.** Requests and limits for the api, chroma and every Job come from `kubectl top` during an ingest, an eval run and a query burst, with the numbers copied into the report.
6. **`k8s/README.md`.** Fresh cluster → working pipeline. Verified once on a new minikube before the demo.
- **Rules:** everything stays in namespace `rahbar` (R12); all A02 security rules still apply (NetworkPolicy, non-root, no secrets). The candidate Deployment gets its own NetworkPolicy allow rules, copied from the api's.

### P6 · Drift and coverage, Part E (Member 1)
1. **E1 live query log** (`eval/live_queries.jsonl`): at least 40 queries, about 28 in the golden set's domain and at least 12 off-topic.
2. **E2 coverage** (`scripts/coverage.py`): the nearest golden question for each live query, and the share above a justified threshold (the paper flags a gap under 85 %). Lists uncovered queries grouped into topics.
3. **E3 data drift.** Ingest Batch B, re-run the Part B suite, and report what changed and why.
4. **E4 close the gap.** Add at least 6 golden questions from the uncovered topics, re-run, and show coverage rising. The script exits non-zero below the threshold.

### P7 · Report, demo and submission (both)
1. **Report PDF** (8 pages or fewer, plus the screenshot appendix): the Figure 3 stage map, the Table 2 qualities, results for Parts A–F, the release decision, answers to Q4 (a)–(f), the contribution table and the AI statement. Names and roll numbers on page 1.
2. **Screenshots** per the brief's list (A, B, C, D, E, F), each showing the command and its uncropped output, labelled by item.
3. **README.** The exact command for each part, A to F.
4. **Demo rehearsal.** On a fresh cluster: the eval Job, opening a trace, and ingesting an unseen batch. Both members run it once each.

## Dependencies and handoffs

| From | To | What | Needed for |
| --- | --- | --- | --- |
| M1 (P1) | M2 | Verification report format and data lake layout | PVC layout, ingestion Job (F2) |
| M2 (P2) | M1 | Trace record with scores and versions | D5 root cause, E3 drift analysis |
| M1 (P3) | M2 | `eval/suite.py` and its result JSON | Gate script (C2), eval Job (F2) |
| M2 (P4 C2) | M1 | Gate config and script | C1 pass and fail runs |
| M1 (P4 C1) | M2 | Candidate settings and collection name | Candidate Deployment (F3) |
| M2 (P5) | Both | Working eval and ingestion Jobs | Every screenshot from the cluster |

P1 and P2 run in parallel from day one. P3 needs P1's Batch B only for its hard questions, so it can start early. P4 waits for P3; P5's Jobs need P1 and P3; P6 needs P3 and Batch B.

## Definition of done

A part is done when all of these hold:
1. Every brief item in it has a command, a committed result file and a screenshot.
2. Its tests are shown to fail without the implementation.
3. `make test`, `make lint` and the CI pipeline are green.
4. The CLAUDE.md §7 checklist is walked.
5. AI-USAGE.md is updated.

**Project done when:**
- [ ] A fresh minikube reaches a working pipeline from `k8s/` and `k8s/README.md` alone.
- [ ] `eval/results/` and `traces/` hold every result the report quotes.
- [ ] The release gate fails one candidate and passes one; a rollout undo trace shows the previous collection.
- [ ] The report is 8 pages or fewer, with the full screenshot appendix.
- [ ] Both members appear in `git shortlog -sn` at 40 % or more, and each can demo every part.

## Resolved questions

| # | Question | Decision |
| --- | --- | --- |
| Q1 | Dates | Out of scope: this plan covers development only |
| Q2 | Which change for Part C? | R10: 200/40 passes; all-minilm fails and is the bad release for the undo demo |
| Q3 | Faithfulness judge | R11: llama3.2:3b on host Ollama, checked against 8 hand labels |
| Q4 | Namespace | R12: keep `rahbar` |
| Q5 | Batch B source | R13: crafted from our own copies of corpus documents plus files we write |
