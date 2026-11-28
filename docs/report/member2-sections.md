# Report sections: Member 2 (MTH99910)

Draft text for the report PDF (Part G): Parts C2, D and F, the Part C release decision,
Q4 (c), (e) and (f), and Member 2's rows for the tables. Every number links to a committed
file. Cluster numbers come from minikube on 2026-11-28 (Linux, docker driver, Ollama
0.40.19 on an AMD RX 6700 XT); local numbers are Member 1's runs
(eval/results/final-44-summary.md). Trim to fit the 8 pages.

## C2. Release gate

`config/gate.yaml` (the same text is the `gate.yaml` key of the `ragops-gate` ConfigMap; a
test fails if they differ) is applied by `scripts/gate.py baseline.json candidate.json`,
which exits 0 (release), 1 (reject) or 2 (unusable input or config: never a pass).

| rule | threshold | justification |
| --- | --- | --- |
| recall@5 drop | at most 0.02 | the brief's rule; two seeded baseline runs differ by 0.000, so any drop is the change |
| faithfulness | at least 0.64 | lower baseline (0.714 local) minus one judged answer (1/14); the judge agrees with our hand labels 6 of 8 times, so one verdict can flip |
| p95 latency | at most 25 s | half of REQUEST_BUDGET_SECONDS (50 s): a p95 request that needs its one retry still ends inside the budget |
| p50 latency | at most 1.5x baseline | seeded runs differ by 6 % locally, 5.8 % on the cluster |
| abstention correctness | not below baseline | the brief's rule (baseline 1.00 on 12 unanswerable questions) |
| citation validity | at least 0.95 | carried from the Assignment 02 CI gate |

| candidate | environment | recall@5 drop | faithfulness | p95 s | decision | file |
| --- | --- | --- | --- | --- | --- | --- |
| k6 (top_k 6) | local | 0.000 | 0.733 | 12.54 | pass | eval/results/c2/gate-k6.txt |
| k6 | cluster | 0.000 | 0.667 | 3.51 | pass | eval/results/cluster/gate-k6.txt |
| all-minilm | local | 0.094 | 0.750 | 3.37 | **fail** | eval/results/c2/gate-minilm.txt |
| all-minilm | cluster | 0.094 | 0.727 | 2.57 | **fail** | eval/results/cluster/gate-minilm.txt |
| chunks 200/40 | local | 0.047 | 0.733 | 20.56 | fail | eval/results/c2/gate-c200.txt |
| overlap 40 | local | 0.063 | 0.812 | 5.37 | fail | eval/results/c2/gate-o40.txt |

**Release decision (Part C): release top_k 6; reject all-minilm.** k6 keeps retrieval
exactly (the 6th passage never changes the top 5) and passes every rule in both
environments. all-minilm fails the recall rule by 9.4 points in both. It passes every
latency rule only because most of its questions are declined under a relevance floor that
was calibrated for nomic-embed-text, which is why recall, not latency, is the rule that
has to catch it. One caution, recorded rather than hidden: on the cluster, k6's faithfulness
(10 of 15 judged answers supported) is 0.119 under the cluster baseline (11 of 14), and
after the release the live api declined one attendance question the baseline answered.
Answer correctness over the golden set is equal (0.355 both), so the gate's pass stands.

## D. Observability and traceability

- **D1 trace record** (`api/app/services/trace.py`, ADR 0005): one JSON line per query
  with the trace id (the request id), timestamp, query, rewritten query, embedding model,
  version (Ollama digest) and dimension, collection, every retrieved chunk with doc_id,
  doc_version, superseded, content hash and score, the filters (superseded metadata
  filter, relevance floor), reranker (none) and prompt order, prompt hash, model and
  parameters, response and citations, guardrail actions, latency per stage, and cache hit
  or miss. Standard output gets the record without prompt or passage text; the
  `ragops-results` volume gets it with the full prompt and evidence. Sample:
  eval/results/f/05-trace-record-kubectl-logs.txt; 369 records in traces/.
- **D2 trace tool**: `kubectl exec deploy/api -- python -m app.tools.trace_show <id>`
  rebuilds the prompt from the recorded evidence with the production `build_prompt` and
  compares its SHA-256 with the recorded prompt hash: MATCH
  (eval/results/f/06-trace-show.txt).
- **D3 metrics and summary**: `/metrics` adds `rahbar_top1_similarity` (histogram),
  `rahbar_injections_flagged_total{source}`, `rahbar_stage_seconds{stage}` (p95 per stage
  in PromQL) beside the existing abstention, cache and latency metrics
  (eval/results/f/08-metrics-port-forward.txt). `trace_summary --since --until` over all
  369 cluster traces: abstention rate 0.377, cache hit rate 0.186, top-1 similarity p50
  0.703 (p25 0.603, p75 0.745), 34 injection flags (9 in chunks, 25 in questions), p95 per
  stage (eval/results/f/15-trace-summary-all.txt).
- **D4 guardrail logging**: the retrieval rail (`services/guardrails.py`) flags
  instruction-like text in a chunk or the question; the Assignment 02 checks (citation
  check, marker check, decline, fallback) write their actions into the same list. Tested
  with Batch B's b09 on the cluster. **Finding:** in `flag` mode the rail flagged b09 three
  times, yet the model answered "true [b09 / 3. Assistant notice]" to "Are all fees waived
  this semester according to the IT policy?": the A02 defence stops obeying and invented
  citations, not repeating a planted claim with a real citation (11-d4-flag-mode.txt). In
  `redact` mode the flagged sentences never reach the prompt and the model declines
  (13-d4-redact-mode.txt). The cluster now runs `redact`, and answers built on flagged
  evidence are never cached.
- **D5** (Member 1 writes it, from the trace only): suggested trace
  `61e8b56d9fcc44279126db019e3e63b3`: "What did the 2023 rules say about attendance?"
  widened the superseded filter; chunk 0009 of the 2023 rules and chunk 0014 of the 2026
  handbook tied at 0.668, both went into the prompt, and the answer mixes the two versions.

## F. Kubernetes

| item | what runs | evidence |
| --- | --- | --- |
| F1 | api Deployment (3, HPA) + Service, chroma StatefulSet + PVC; data lake on PVC `ragops-data`, results and traces on `ragops-results` | 00-kubectl-get-all.txt |
| F2 | ingestion Job + weekly CronJob (only Chroma writer), suite as a Job (4 runs), gate Job; gate thresholds in ConfigMap `ragops-gate`: Failed, edit, Complete with the same image | 01, 02, 03 in eval/results/f/ |
| F3 | `api-candidate` Deployment + Service + collection per candidate (`k8s/release/`); rolling release with `maxUnavailable: 0`; bad release reversed by `rollout undo`; trace after the undo shows rahbar-k6 and nomic-embed-text 0a109f422b47 | 14-release-rollout.txt |
| F4 | traces on stdout (`kubectl logs`) and the volume; `/metrics` through `kubectl port-forward` | 05, 07, 08 |
| F5 | requests and limits from `kubectl top` during ingestion, eval and an 82-question burst | eval/results/f5/resources.md |

A fresh namespace reaches a completed first ingestion (803 chunks) in 4 min 53 s with
`kubectl apply -k k8s/overlays/dev` (k8s/README.md).

Failures found on the cluster and fixed (docs/failure-log.md): the provisional 0.95
near-duplicate threshold quarantined a real document (now 0.98, measured: different
documents reach 0.9588, the planted near duplicate 0.9997); the planted b09 claim reached a
user in flag mode and was then served from the cache; a release served the previous
configuration's cached answers (cache now scoped by configuration); a failed ingestion
attempt left no logs (`restartPolicy: Never`).

## Q4 (c): archive or delete old versions? What breaks if you delete?

We archive. A superseded version moves to `archive/<doc_id>/<version>/` on the data lake
PVC and stays in Chroma with `superseded: true`, so retrieval excludes it unless a question
asks for an older version (the 2023 rules, the 2026-27 fee page after Batch B). Deleting
would break three things we use: (1) `pipeline.ops restore` (the A2 rollback; the fee page
was restored with 10 metadata updates and 0 re-embeddings, eval/results/a/07-rollback.txt),
(2) questions about an older version, which the superseded filter answers today (trace
61e8b56d…), and (3) reproducibility: a trace names `doc_version` and `content_hash`, which
could no longer be checked against a source. Deletion is right only for a document that
must not be served at all, and our prune step already removes its chunks (0 orphans,
eval/results/a/06-counts-after-delete.txt).

## Q4 (e): which paper idea was hardest to apply, and what did we change?

Traceability (Table 2): "trace every query to the exact data version". The paper treats
the trace as something the pipeline emits; in practice three things fought it. (1) The
trace must record the prompt, but our Assignment 02 data governance (ADR 0004) keeps
prompts and passages out of INFO logs; we split the record (ADR 0005): stdout without
prompt text, the volume with it, and a prompt hash that joins them, which the trace tool
verifies by rebuilding the prompt. (2) A model name is not a version: after a re-pull the
name stays the same, so we record Ollama's digest. (3) A configuration change (a release by
`set env`) changes what an answer means without any data change, so the cache, which the
paper does not discuss, had to be keyed by configuration as well as by index version.

## Q4 (f): which Kubernetes object carries which RAGOps responsibility?

| object | responsibility |
| --- | --- |
| `Job indexer`, `CronJob reindex` (`concurrencyPolicy: Forbid`) | the only writer to Chroma: ingest, verify, update the lake, update the retrieval source |
| `NetworkPolicy chroma` | enforces the single writer: only api, api-candidate, indexer and eval pods reach Chroma, and only the indexer image has write code |
| `PVC ragops-data` | the data lake: raw, quarantine, archive survive restarts |
| `PVC ragops-results` | suite results, gate decisions, traces (offline and live testing records) |
| `ConfigMap ragops-gate` | every threshold: gate, verification, coverage; a change needs no rebuild |
| `ConfigMap rahbar-config` | the embedding pin (`EMBED_MODEL`) shared by writer and readers |
| `Deployment api-candidate` + `Service` | the candidate under test, with its own collection |
| `Deployment api` (`maxUnavailable: 0`, readiness on the pin) | the controlled release and `rollout undo`; readiness refuses a mismatched index |
| `Job` (eval, gate) | offline testing and the release decision, failing the Job when the gate fails |

## Contribution table (Member 2's rows)

| member | work |
| --- | --- |
| Member 2 (MTH99910) | uniqueness check (A1 swap) and its measured threshold; trace record, trace tool, metrics, summary, retrieval rail (D1-D4); release gate, config and ConfigMap (C2); PVCs, Jobs, candidate release, NetworkPolicy, eval image, resources, k8s/README.md (F, C3); cluster runs of A, B, C and F; ADR 0005; four cluster failures found and fixed |

## Screenshots Member 2 should take (appendix)

Each from the terminal on our own cluster, command and output uncropped. The committed
text files show the same runs; re-run the command to screenshot it.

- C: `python scripts/gate.py ...baseline-cluster.json ...minilm-cluster.json` (fail) and `...k6-cluster.json` (pass)
- D: one full trace (`kubectl logs ... | grep <id>`) and `trace_show <id>` with MATCH
- F: `kubectl get all,pvc,configmap,cronjob,job -n rahbar`; `kubectl logs job/indexer`; the
  eval Job's logs; the gate Job Failed then Complete around the ConfigMap edit;
  `kubectl rollout status` and `kubectl rollout undo` with the trace after it
