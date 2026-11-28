# k8s/: fresh cluster to a working RAGOps pipeline

Everything runs in namespace `rahbar`. Commands are run from the repository root. Where
PowerShell (Windows) differs from bash, both are given. `make` targets are shortcuts for
the same commands; Windows without `make` can type the commands.

| Object | RAGOps responsibility |
| --- | --- |
| `Deployment api` (3 replicas, HPA, `maxUnavailable: 0`) | the live query path; writes one trace per query to stdout and `/results/traces` (D1, F4); released and rolled back with `kubectl set env` / `rollout undo` (F3) |
| `StatefulSet chroma` + its PVC | the vector store (F1) |
| `Job indexer`, `CronJob reindex` | ingestion with verification (A1, A2), **the only writer to Chroma** (R9): nothing else has the code, the NetworkPolicy path and the data lake |
| `PVC ragops-data` | the data lake: `raw/`, `incoming/`, `quarantine/`, `archive/`, `reports/` (F1) |
| `PVC ragops-results` | suite results, gate decisions, traces (F2, F4) |
| `ConfigMap ragops-gate` | every threshold: gate rules (`gate.yaml`), verification, coverage (R6) |
| `ConfigMap rahbar-config` | pipeline settings shared by api and indexer, incl. the `EMBED_MODEL` pin |
| `Deployment/Service api-candidate`, `Job index-rahbar-<name>` (`k8s/release/`) | the candidate and its own collection (F3) |
| `Job ragops-eval` (`k8s/eval-job.yaml`, Member 1) | the Part B suite + the gate; fails when the gate fails (F2) |
| `Job ragops-gate` (`k8s/gate-job.yaml`) | the gate alone, on result files already on the volume (C2, F2 demo) |
| `NetworkPolicy` (deny by default) | who may reach Chroma (api, api-candidate, indexer, eval only) |

## 0. Once per laptop

- Docker (Desktop on Windows), minikube, kubectl.
- Ollama on the host with the three models, listening on all interfaces so pods reach it
  as `host.minikube.internal:11434`:

  ```bash
  ollama pull llama3.2:3b; ollama pull nomic-embed-text; ollama pull all-minilm
  # Windows: set the user variable OLLAMA_HOST=0.0.0.0 and restart Ollama from the tray.
  # Linux:   OLLAMA_HOST=0.0.0.0 ollama serve, or Ollama in Docker, e.g. on an AMD GPU:
  #   docker run -d --name ollama --device /dev/kfd --device /dev/dri -e OLLAMA_HOST=0.0.0.0 \
  #     -e HSA_OVERRIDE_GFX_VERSION=10.3.0 -p 11434:11434 -v ollama-models:/root/.ollama \
  #     ollama/ollama:0.40.19-rocm
  #   docker exec ollama ollama pull llama3.2:3b   (and the two embedding models)
  ```

  The NetworkPolicy allows Ollama at `192.168.65.254` (Docker Desktop) and `192.168.49.1`
  (Linux docker driver). Check yours with
  `minikube ssh "grep host.minikube.internal /etc/hosts"`; anything else needs one more
  `ipBlock` in `k8s/base/networkpolicy.yaml`.

## 1. Fresh cluster to a working pipeline

```bash
make cluster                       # minikube start --driver=docker --cni=calico --memory=6144 --cpus=4
                                   # + addons metrics-server and ingress
make images                        # builds rahbar-api, -indexer, -ui, -eval :dev and loads them
kubectl apply -k k8s/overlays/dev  # namespace, PVCs, ConfigMaps, chroma, redis, api, ui, Jobs, policies
kubectl wait -n rahbar --for=condition=complete job/indexer --timeout=30m
kubectl rollout status -n rahbar deployment/api
kubectl get all,pvc,configmap,cronjob,job -n rahbar        # F screenshot 1
```

Verified on a fresh minikube (Linux, docker driver) on 2026-11-28: from an empty namespace
to a completed first ingestion (803 chunks) in 4 min 53 s
(eval/results/f/01-ingestion-job-first-run.txt). The `rahbar-secret` Secret is optional
(the api reads it only with `LLM_PROVIDER=hosted`; see the root README).

Without `make` (PowerShell), `make images` is:

```powershell
docker build -t rahbar-api:dev api
docker build -t rahbar-indexer:dev -f indexer/Dockerfile .
docker build -t rahbar-ui:dev ui
docker build -t rahbar-eval:dev -f eval/Dockerfile .
foreach ($i in "api","indexer","ui","eval") { minikube image load "rahbar-${i}:dev" }
```

`eval/Dockerfile` needs BuildKit (Docker Desktop has it; on Linux install the
`docker-buildx` plugin), because its file list is `eval/Dockerfile.dockerignore`.

Ask a question through the Ingress (on Windows or macOS run `minikube tunnel` in a second
terminal and use 127.0.0.1 instead of `$(minikube ip)`):

```bash
curl -s -X POST "http://$(minikube ip)/api/ask" -H "Host: rahbar.local" -H "Content-Type: application/json" -d '{"question": "What CGPA puts a student on academic warning?"}'
```

PowerShell: `Invoke-RestMethod -Method Post -Uri http://127.0.0.1/api/ask -Headers @{Host="rahbar.local"} -ContentType application/json -Body '{"question": "What CGPA puts a student on academic warning?"}'`

The response's `request_id` is the trace id.

## 2. Part A on the cluster: ingestion Job, verification, an unseen batch

```bash
kubectl logs -n rahbar job/indexer                   # the verification table and the counts
make index                                           # re-run from the CronJob: "embedded": 0 on an unchanged corpus
kubectl apply -f k8s/tools/ragops-shell.yaml         # a pod with both volumes, for kubectl cp
kubectl wait -n rahbar --for=condition=Ready pod/ragops-shell
kubectl exec -n rahbar ragops-shell -- mkdir -p /data/incoming
for f in corpus/batch_b/b*.md corpus/batch_b/b*.pdf corpus/batch_b/b*.txt; do kubectl cp "$f" "rahbar/ragops-shell:/data/incoming/$(basename "$f")"; done
kubectl create job --from=cronjob/reindex ingest-batch-b -n rahbar   # intake -> verify -> quarantine/archive -> sync
kubectl wait -n rahbar --for=condition=complete job/ingest-batch-b --timeout=30m
kubectl logs -n rahbar job/ingest-batch-b                            # A screenshot: the verification table
kubectl exec -n rahbar ragops-shell -- python -m pipeline.ops status
kubectl exec -n rahbar ragops-shell -- ls /data/quarantine /data/reports
```

PowerShell, the copy loop:
`Get-ChildItem corpus/batch_b/b* -Include *.md,*.pdf,*.txt | ForEach-Object { kubectl cp $_.FullName "rahbar/ragops-shell:/data/incoming/$($_.Name)" }`
(if kubectl cp rejects the drive letter, `cd corpus/batch_b` first and pass `$_.Name`).

Expected (measured, eval/results/f/09-batch-b-ingestion-job.txt): b02, b04 (exact
duplicates), b05 (near duplicate), b06, b07, b11 quarantined; the 2026-27 fee page archived
for b08; 21 chunks embedded, 793 unchanged.

`make index` is `kubectl create job --from=cronjob/reindex reindex-<time> -n rahbar`.
Build the candidate collections (section 4) **before** Batch B goes into `incoming/`.

## 3. Part D on the cluster: traces, the trace tool, metrics

```bash
kubectl logs -n rahbar -l app=api --tail=-1 | grep '"msg": "trace"'      # D1/F4: JSON lines on stdout
kubectl exec -n rahbar deploy/api -- python -m app.tools.trace_show <trace_id>     # D2 (= make trace ID=...)
kubectl exec -n rahbar deploy/api -- python -m app.tools.trace_summary --since 2026-11-28T10:00   # D3
kubectl port-forward -n rahbar svc/api 8000:8000 ; curl -s localhost:8000/metrics | grep -E "rahbar_(top1|injections|stage|abstentions|cache_hit)"
kubectl cp rahbar/ragops-shell:/results/traces ./traces                  # commit samples (R5)
```

The trace id is the response's `request_id` (also the `X-Request-ID` header).

## 4. Parts C and F: gate, candidate, controlled release

```bash
# the candidate and its own collection (R9: built by an indexer Job)
kubectl apply -k k8s/release/minilm          # Job index-rahbar-minilm + Deployment/Service api-candidate
kubectl wait -n rahbar --for=condition=complete job/index-rahbar-minilm --timeout=30m
kubectl rollout status -n rahbar deployment/api-candidate
# the eval Job against http://api-candidate:8000, then the gate. k8s/eval-job.yaml is
# Member 1's (the plan's swap task); it runs the rahbar-eval image with label
# app: ragops-eval, mounts ragops-results at /results and the ragops-gate ConfigMap at /config.
kubectl apply -f k8s/eval-job.yaml           # Failed: minilm is stopped by the gate, never rolled out

kubectl apply -k k8s/release/k6              # the passing candidate replaces it as api-candidate
kubectl wait -n rahbar --for=condition=complete job/index-rahbar-k6 --timeout=30m
kubectl apply -f k8s/eval-job.yaml           # Complete: the gate passes
```

**Gate threshold from the ConfigMap, no rebuild (F2).** With two result files on the volume:

```bash
kubectl apply -f k8s/gate-job.yaml                       # minilm vs baseline -> Failed
kubectl logs -n rahbar job/ragops-gate
kubectl edit configmap ragops-gate -n rahbar             # gate.yaml: recall_at_5 max_drop 0.02 -> 0.10
kubectl delete job ragops-gate -n rahbar
kubectl apply -f k8s/gate-job.yaml                       # same image, same files -> Complete
kubectl apply -k k8s/overlays/dev                        # put the committed threshold back
```

Measured: eval/results/f/03-gate-configmap-edit.txt (Failed, then Complete, same image).
For the baseline numbers the gate compares against, `kubectl apply -k k8s/release/baseline`
runs the live settings on `api-candidate` (no cache, like every candidate).

**Release the passing candidate with a rolling update (F3).** The live Deployment gets the
values the gate tested; `maxUnavailable: 0` keeps three ready pods throughout.

```bash
kubectl set env deployment/api -n rahbar CHROMA_COLLECTION=rahbar-k6 TOP_K=6
kubectl annotate deployment/api -n rahbar kubernetes.io/change-cause="release k6 (gate pass)" --overwrite
kubectl rollout status deployment/api -n rahbar
```

**A bad release, reversed (F3).** all-minilm is pushed to the live Deployment on purpose,
bypassing the gate, then undone. `set env` (not a ConfigMap edit) creates a new ReplicaSet,
so there is a revision to undo, and the indexer's ConfigMap stays untouched.

```bash
kubectl set env deployment/api -n rahbar EMBED_MODEL=all-minilm CHROMA_COLLECTION=rahbar-minilm
kubectl annotate deployment/api -n rahbar kubernetes.io/change-cause="bad release: all-minilm" --overwrite
kubectl rollout status deployment/api -n rahbar
sleep 10   # ingress-nginx keeps the old pods in its endpoints for a few seconds
# ask one question: its trace shows collection rahbar-minilm, embedding all-minilm
kubectl rollout undo deployment/api -n rahbar
sleep 3; kubectl rollout status deployment/api -n rahbar   # without the pause it can report done before the undo starts
sleep 10
kubectl rollout history deployment/api -n rahbar
# ask again: the new trace shows rahbar-k6 and nomic-embed-text with its digest
```

Measured: eval/results/f/14-release-rollout.txt (three ready pods throughout; traces
before, after the release, after the bad release, and after the undo).

`kubectl set env` adds `env` entries that `kubectl apply -k` does not remove. To go back to
the ConfigMap's values: `kubectl set env deployment/api -n rahbar CHROMA_COLLECTION- TOP_K- EMBED_MODEL-`.
To keep a release, commit it to `k8s/base/configmap.yaml`, so the CronJob also maintains
the released collection. Cache entries are keyed by the configuration, so a release or an
undo never serves the other configuration's cached answers (docs/failure-log.md).

## 5. F5: resources

`kubectl top pods -n rahbar` during an ingestion, an eval run and a query burst; the
numbers and the requests and limits chosen from them are in `eval/results/f5/`.

## Troubleshooting

In this order: `kubectl get pods -n rahbar` → `kubectl describe pod` (Events) →
`kubectl logs` (`--previous` after a crash). Common ones:

- api not ready, `/readyz` names `embedding pin`: the collection was built with another
  `EMBED_MODEL`. Expected for a candidate until its index Job completes.
- Job stuck `ContainerCreating`: the PVC is not bound (`kubectl get pvc -n rahbar`);
  minikube's `storage-provisioner` addon must be enabled.
- Indexer `ConnectError` to Ollama: Ollama listens on 127.0.0.1 only, or the host IP is
  not in the NetworkPolicy (section 0).
- `field is immutable` when re-applying a Job: `kubectl delete job <name> -n rahbar` first.
- A `rahbar-config` change (e.g. `GUARDRAIL_INJECTION_ACTION`) reaches the api only after
  `kubectl rollout restart deployment/api -n rahbar`.
- `kubectl cp` needs `tar` in the pod: use `ragops-shell` (the indexer image), not chroma.
