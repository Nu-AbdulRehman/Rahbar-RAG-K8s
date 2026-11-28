# Handover: Member 2's RAGOps work, for Member 1

Answers docs/handover/HANDOVER-ragops-m1.md. Branches, stacked in this order, each with a
PR into `dev`: `ragops/a1-uniqueness` → `ragops/d-tracing` → `ragops/c2-gate` →
`ragops/f-kubernetes`. Everything below was run on a fresh minikube (Linux, docker driver,
Ollama 0.40.19 on an AMD GPU) on 2026-11-28; evidence in `eval/results/f/`,
`eval/results/cluster/`, `eval/results/f5/` and `traces/`.

## Status by part

| Part | Item | Status | Where |
| --- | --- | --- | --- |
| A1 | uniqueness: exact (SHA-256 of text) and near (document embedding cosine >= 0.98) | done; Batch B b02, b04, b05 quarantined on the cluster | indexer/pipeline/verify.py, eval/results/a/09-uniqueness-threshold.txt |
| C2 | config/gate.yaml, ragops-gate ConfigMap, scripts/gate.py | done; k6 passes, minilm/c200/o40 fail, locally and on the cluster | eval/results/c2/, eval/results/cluster/ |
| C3/F3 | api-candidate per candidate, rolling release, bad release, rollout undo with traces | done | k8s/release/, eval/results/f/14-release-rollout.txt |
| D1-D4 | trace record, trace_show, metrics + trace_summary, retrieval rail in the trace | done | api/app/services/trace.py, guardrails.py, api/app/tools/ |
| D5 | root cause from a trace | **yours**: trace id below | |
| F1, F2, F4, F5 | PVCs, ingestion Job/CronJob on the lake, gate Job, traces on the volume, measured resources | done | k8s/base/, k8s/gate-job.yaml, eval/results/f5/resources.md |
| F2 | `k8s/eval-job.yaml` | **yours** (swap task): everything it needs exists, see below | |
| F | k8s/README.md | done, verified from an empty namespace (4 min 53 s to 803 chunks) | |
| B, C1 on the cluster | suite as Jobs: baseline (2 seeded runs), k6, minilm | done with an ad-hoc Job (not committed: eval-job.yaml is yours) | eval/results/cluster/ |
| A on the cluster | first ingestion, unchanged re-run (embedded 0), Batch B through the Job | done | eval/results/f/01, 02, 09 |
| E on the cluster | query_coverage as a Job | not run: it needs your eval Job (same image) | |
| G | report text for C2, D, F, Q4 c, e, f | drafted | docs/report/member2-sections.md |

## Screenshots (Member 2's appendix items, taken)

`docs/report/screenshots/` holds C2 (gate fail, gate pass), D1 (full trace record), D2
(trace tool with MATCH), and F (get all; ingestion Job logs; an evaluation Job's logs;
the gate Job before and after a ConfigMap edit; rollout status; bad release; rollout undo
with the trace showing the previous collection and embedding version). Its README.md maps
each file to its label and command; `transcripts/` has the text. Still to take, by you: A
(the unchanged-corpus run with 0 embedded; the Batch B report is covered by
F2-ingestion-job-logs), B, E, and the eval Job logs again once `k8s/eval-job.yaml` exists.

## The eval image (the decision you were waiting for)

`eval/Dockerfile`, built **from the repository root**: `docker build -t rahbar-eval:dev -f
eval/Dockerfile .` (`make images` builds and loads it). It needs BuildKit (Docker Desktop
has it) because its allowlist is `eval/Dockerfile.dockerignore`. Layout in the image is the
repository's, so every script runs unchanged:

    /app/api/app            the api package (suite.py imports it)
    /app/eval/              suite.py, run_eval.py, ragops_metrics.py, query_coverage.py,
                            golden.jsonl, embedding_pairs.jsonl, live_queries.jsonl
    /app/scripts/gate.py    /app/config/gate.yaml (the ConfigMap's copy goes to /config)

Non-root (10001), works with `readOnlyRootFilesystem: true` and an emptyDir at `/tmp`.

What `k8s/eval-job.yaml` needs to work with what is already there (this is exactly what
the ad-hoc runs used, minus the gate step):

- **label `app: ragops-eval`** on the pod: the `ragops-eval` NetworkPolicy lets it reach
  api, api-candidate, chroma and Ollama; nothing else is allowed.
- `envFrom: rahbar-config` and `ragops-gate`, then `env` overrides for the candidate:
  `CHROMA_COLLECTION`, `EMBED_MODEL`, `TOP_K`, and `EMBED_TIMEOUT_SECONDS=60`.
- volumes: PVC `ragops-results` at `/results`; ConfigMap `ragops-gate` (item `gate.yaml`) at
  `/config` (`GATE_CONFIG=/config/gate.yaml` comes from the ConfigMap); emptyDir at `/tmp`.
- command: `python eval/suite.py --api http://api-candidate:8000 --collection <coll>
  --label <label> --out-dir /results/eval`, then `python scripts/gate.py <baseline file>
  <the new file> --out /results/gate/<name>.json`, in one `sh -c ... && ...`, so the Job
  fails when the gate fails. `k8s/gate-job.yaml` shows how to pick the newest file by label
  (`ls -t /results/eval/*-<label>.json | head -n 1`).
- `restartPolicy: Never`, `backoffLimit: 0` (a gate failure is an answer, not a crash).
- resources, measured: suite peak 91m CPU, 93Mi; use requests 100m/128Mi, limits
  500m/256Mi (eval/results/f5/resources.md).
- The baseline file on the volume: `20261128T105812Z-baseline-cluster.json` (or re-run it
  with `kubectl apply -k k8s/release/baseline` and your Job against api-candidate).

## For D5: a trace with scores and versions

`61e8b56d9fcc44279126db019e3e63b3`: "What did the 2023 rules say about attendance?". The
old-version router widened the superseded filter; `undergraduate-academic-rules-aug-2023.pdf#0009`
(2023-08, superseded) and `academic-rules-handbook-jun-2026.pdf#0014` (2026-06) tied at
0.668 and both went into the prompt; the answer mixes the two versions. Read it with
`python scripts/trace_show.py 61e8b56d9fcc44279126db019e3e63b3 --dir traces`
(eval/results/f/06-trace-show.txt). traces/README.md lists the other notable traces.

## Things you will see in the numbers

1. **Cluster recall@5 is 0.562, not 0.688.** Not a regression: the cluster runs use
   golden.jsonl after your relabelling of q10, q14, q15, q21, q22 to the 2027-28 fee
   schedule, which a pre-Batch-B collection cannot answer. The suite was run before Batch B
   went in, as your handover asked. Compare cluster runs with cluster runs.
2. **k6 on the cluster:** faithfulness 0.667 (10 of 15) against the baseline's 0.786
   (11 of 14); answer correctness equal (0.355). After the live release, one attendance
   question was declined that the baseline answers. The gate passes it; your C1 write-up
   may want to say why one more passage can make llama3.2:3b decline.
3. **The rail and the cache (D4):** flag mode let b09's "fees are waived" through with a
   valid citation, and the cache then served it. The cluster runs `redact` now, flagged
   answers are never cached, and cache entries are scoped by configuration
   (docs/failure-log.md, three entries).
4. **The uniqueness threshold is 0.98, not 0.95:** 0.95 quarantined the prospectus
   (cosine 0.954 with the 2023 rules). Pairs measured with `python -m pipeline.ops
   similarities`.

## Changes in your area (please review)

- `indexer/pipeline/run.py`, `verify.py`, `config.py`, `ops.py` (uniqueness, the swap task).
- `api/app/services/answer.py`, `generation.py` (trace and guardrail events; behaviour
  unchanged except: answers on flagged evidence are not cached).
- `api/app/providers/cache/` (entries scoped by configuration; three tests now name the
  scoped key `rahbar:cache:entries:0:default`, same assertions).
- `corpus/batch_b/README.md` (the "until uniqueness lands" paragraph replaced by results).

## Traps

- `fetch.py` downloads what `raw/` is missing, so every run re-downloads each archived
  document (the 2023 rules are 14.8 MB) and, after Batch B, the old fee page. Harmless for
  correctness (refresh() ignores the copy), slow on a bad connection. Yours to decide.
- A `rahbar-config` change reaches the api only after `kubectl rollout restart
  deployment/api`; the cache is not invalidated by it (entries for the new configuration
  start empty, which is now correct).
- Jobs are immutable: `kubectl delete job <name>` before re-applying one.
- On Linux, `host.minikube.internal` is 192.168.49.1; both it and Docker Desktop's
  192.168.65.254 are in the NetworkPolicy.
