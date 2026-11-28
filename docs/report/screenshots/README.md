# Screenshots for the report appendix (Member 2: Parts C, D, F)

Taken on 2026-11-28 on our own minikube cluster (namespace `rahbar`), in a fullscreen
Konsole on Member 2's laptop. Each command was run in that terminal and its output shown
uncropped; output longer than one screen is split into consecutive pages (`-a`, `-b`,
`-c`), and every page after the first starts with a grey `[name, continued: lines x-y of
n]` line. The plain text of each run is in `transcripts/`.

| label | file(s) | command | what it shows |
| --- | --- | --- | --- |
| C2 gate fail | C2-gate-fail.png | `python scripts/gate.py <baseline-cluster> <minilm-cluster>` | all-minilm rejected: recall@5 drops 9.4 points; exit code 1 |
| C2 gate pass | C2-gate-pass.png | `python scripts/gate.py <baseline-cluster> <k6-cluster>` | top_k 6 passes every rule; exit code 0 |
| D1 trace record | D1-trace-record-a/b/c.png | ask through the Ingress, then `kubectl logs -l app=api \| grep <trace id> \| python3 -m json.tool` | one full trace record from stdout: every D1 field |
| D2 trace tool | D2-trace-tool-a/b.png | `kubectl exec deploy/api -- python -m app.tools.trace_show <same trace id>` | chunks with versions and scores, filters, and the prompt rebuilt from the trace: prompt hash MATCH |
| F get all | F1-get-all-a/b.png | `kubectl get all,pvc,configmap,cronjob,job -n rahbar` | Deployments, StatefulSet, Services, HPA, PVCs, ConfigMaps, CronJob, Jobs |
| F ingestion Job | F2-ingestion-job-logs-a/b.png | `kubectl logs job/ingest-batch-b` | completed ingestion of Batch B: verification table (6 quarantined, with reasons), 21 embedded, 793 unchanged. Also serves as Part A's Batch B report |
| F evaluation Job | F2-eval-job-logs.png | `kubectl logs job/suite-baseline-cluster` | a completed suite Job: three-level summary, stochasticity of two seeded runs. Member 2's run; Member 1's `k8s/eval-job.yaml` can replace it |
| F gate + ConfigMap (before) | F2-gate-configmap-a.png | `kubectl apply -f k8s/gate-job.yaml` | the gate Job Failed: GATE FAIL with max_drop 0.02 |
| F gate + ConfigMap (after) | F2-gate-configmap-b.png | edit `ragops-gate` (max_drop 0.10), re-run the same Job | same image, same files: Complete, GATE PASS |
| F rollout status | F3-rollout-status.png | `kubectl set env ... CHROMA_COLLECTION=rahbar-k6 TOP_K=6`, `kubectl rollout status` | the passing candidate released by a rolling update |
| F bad release | F3-bad-release.png | `kubectl set env ... EMBED_MODEL=all-minilm CHROMA_COLLECTION=rahbar-minilm`, rollout status, a trace | trace: rahbar-minilm, all-minilm 1b226e2802db, dimension 384 |
| F rollout undo | F3-rollout-undo.png | `kubectl rollout undo`, rollout status, history, a new trace | trace after the undo: the previous collection rahbar-k6 and embedding nomic-embed-text 0a109f422b47 |

Parts A, B and E are Member 1's screenshots (the F ingestion screenshot also shows A's
Batch B verification report).

The two `sleep`s in the F3 screenshots are deliberate (docs/failure-log.md): `rollout
status` straight after `rollout undo` can report done before the controller sees the undo,
and ingress-nginx keeps sending requests to the old pods for a few seconds after a rollout.
