# Failure log

Appended when something breaks, not afterwards. Feeds engineering note Q7.

| Date | Symptom | Cause | Fix |
| --- | --- | --- | --- |
| 2026-11-07 | Embedding one question timed out (httpx.ReadTimeout after EMBED_TIMEOUT_SECONDS=10) while a chunk-config re-index was embedding 550 chunks | Indexer and api share one Ollama host (D2). Ollama queued the single question behind the indexer's 32-text batches | Expected behaviour, not a fix: the api turns the timeout into the canned answer, never a 500. On the cluster, run re-indexes off-peak (the weekly CronJob), and watch rahbar_fallbacks_total{reason="retrieval"} during a reindex |
| 2026-11-07 | First real question took 2 min 12 s; the log showed `provider call failed ... ReadTimeout` on attempt 1 | llama3.2:3b loads into the GPU on the first call, which took longer than LLM_TIMEOUT_SECONDS=120. Attempt 2 answered in 8 s | The single retry absorbed it. On the cluster, warm the model before traffic (one `ollama run llama3.2:3b ""` on the host), or keep it loaded with OLLAMA_KEEP_ALIVE |
| 2026-11-07 | The same answer said "2.00" with a valid citation but `answered_from_context: false`, so the UI would show "Not covered" | The prompt only said when to set the flag false, and the 3B model read it as optional | Rule 2 of the instructions now defines the flag both ways (api/app/services/prompt.py) |
| 2026-11-07 | Audit: a worst-case /api/ask could run about 200 s (two 60 s answer attempts, a 60 s summary call, embeddings) | Each timeout was per call, with nothing bounding the whole request; nginx-ingress returns 504 after 60 s, so the user would see a 5xx | REQUEST_BUDGET_SECONDS=50 bounds the request (api/app/services/generation.py, `remaining`); a cold model load now costs one canned answer instead of a 504 |
| 2026-11-07 | `minikube start --memory=6144` refused: "Docker Desktop has only 5778MB memory" | Docker Desktop's VM on this laptop is capped below the brief's 6 GB | Started with `--memory=5120`; the Makefile takes `MINIKUBE_MEMORY` so the default stays 6144 |
| 2026-11-07 | chroma-0 in CrashLoopBackOff on first apply: `invalid type: found string "tcp://10.106.193.222:8000", expected u16 for key "PORT" in CHROMA_ environment variable(s)` | Kubernetes service links: the Service named `chroma` injects `CHROMA_PORT=tcp://...` into every pod in the namespace, and Chroma 1.0 reads any `CHROMA_*` variable as its own config | `enableServiceLinks: false` on every pod spec in k8s/base; nothing uses the injected variables, the apps use Service DNS names |
| 2026-11-07 | All three api pods in CrashLoopBackOff at the same time: `ValueError: Could not connect to a Chroma server` then `Application startup failed` | `chromadb.HttpClient` contacts the server when it is built, and the retriever built it in the FastAPI lifespan. A Chroma that is down at boot killed the process instead of failing readiness (§4.3) | `ChromaRetriever.client` connects on first use (api/app/retrieval/chroma.py); /readyz returns 503 naming chroma until it answers. Test: test_a_chroma_that_is_down_at_boot_leaves_the_api_alive_and_not_ready |
| 2026-11-07 | `kubectl apply -k` after editing the indexer: `The Job "indexer" is invalid: spec.template ... field is immutable` | A Job's pod template cannot change after creation | Delete the finished Job first (`kubectl delete job indexer -n rahbar`), then apply. Re-indexing uses `kubectl create job --from=cronjob/reindex`, which never hits this |
| 2026-11-07 | CI scan failed for all three images: `Unable to resolve action aquasecurity/trivy-action@0.33.1, unable to find version 0.33.1` | trivy-action tags carry a v prefix (v0.33.1); the pin was written without it and never resolved | Pinned to aquasecurity/trivy-action@v0.36.0, and checked every action pin in ci.yml and cd.yml against the GitHub tags API |
| 2026-11-07 | e2e-eval on GitHub: `error: timed out waiting for the condition on jobs/indexer` after 10 min, and no indexer pod in `kubectl get pods`, yet the api pods were ready | On a fresh kind cluster the fixture Job (3 s of work) reaches its last step, the Redis cache bump, before Redis has pulled its image. With backoffLimit 2 the quick in-place restarts exhausted the limit, the Job was marked Failed and the controller deleted the pod, so there were no logs to read. My first local reproduction was wrong: the test Job read the dev ConfigMap and failed on "no documents found in /corpus" | k8s/overlays/e2e sets backoffLimit 6 for the fixture Job. Reproduced properly with Redis scaled to 0 for 40 s: Complete after 3 restarts, one more than the base limit allows |
| 2026-11-07 | README run on a fresh minikube: all three api pods restarted once (`Container api failed startup probe, will be restarted`), then came up | The startup embedding-pin check ran Chroma I/O inside the FastAPI lifespan. With chroma still pulling its image the Service had no endpoints and the connect hung about 75 s, past the 60 s startup probe, so uvicorn never served /healthz in time | The startup check runs in a daemon thread (api/app/main.py); /readyz still refuses until the pin matches. Reproduced with chroma at 0 replicas: the new pod stayed alive at 0/1 with 0 restarts for 100 s. Test: test_a_hung_chroma_at_boot_does_not_hold_up_startup |
| 2026-11-07 | First cd.yml run on main: build-push pushed all three images, then deploy timed out on `job/indexer`; api, ui and indexer pods in ImagePullBackOff on `docker.io/nuabdulrehman/rahbar-*:set-by-cd` | The deploy ran `kustomize edit set image rahbar-api=...` in k8s/overlays/ci, but the prod overlay underneath had already renamed rahbar-api to docker.io/nuabdulrehman/rahbar-api, so the ci-level image transform matched nothing and the placeholder tag shipped. My earlier minikube rehearsal of the smoke test pointed the ci overlay at the dev overlay instead of prod, so it never exercised this | The pin step edits k8s/overlays/prod (where the names are mapped) and renders through ci; a guard fails the job if any rahbar image is not tagged with the commit SHA. Reproduced and verified with kustomize v5.8.3 |
| 2026-11-27 | PR #32 (docs only) failed `scan (rahbar-ui)`: Trivy found 4 CRITICAL and 2 HIGH in nginx 1.30.6-r1 (CVE-2026-113425, -121810, -123007, -123633, -118899, -123634), fixed in 1.30.7-r0 | New nginx CVEs published after the base image was pinned; nginx in nginx-unprivileged comes from nginx.org, so the Dockerfile's `apk upgrade` does not move it, and no 1.30.7-alpine tag existed yet | ui/Dockerfile moves to nginxinc/nginx-unprivileged:1.31.7-alpine (nginx 1.31.7); local Trivy exit 0, page and /healthz still served read-only. Committed by Nu-AbdulRehman on the plan branch as a one-time exception to the account split, at the user's request |
| 2026-11-28 | First real RAGOps ingestion: `pipeline.ops counts` listed chunks by file name, and the two academic-rules versions did not share their doc_id | clean() rebuilt the Document from four positional fields and dropped the new doc_id and title, so every chunk fell back to its source name | clean() uses dataclasses.replace(doc, pages=...); test_cleaning_keeps_the_document_identity fails without it. The next run updates 803 chunks' metadata without re-embedding |
| 2026-11-28 | First RAGOps baseline: embedding 2.2 s per chunk and a 28 s median answer, about 10x the Assignment 02 numbers on the same laptop | `ollama ps` showed "100% CPU" and the server log `total_vram="0 B"`: the reinstalled Ollama, started with `ollama serve` from Git Bash, did not discover the RTX 3050 (nvidia-smi and the bundled cuda_v12/v13 libraries were fine) | Restarted the server from PowerShell (Start-Process); the log then shows `library=CUDA ... total_vram="6.0 GiB"` and `ollama ps` "100% GPU". A second cause came out on the re-run, which timed out on its first embedding: `localhost` resolves to IPv6 ::1 first, Ollama listens on IPv4 127.0.0.1 only, and httpx waits about 2 s on every request before falling back (curl 0.28 s, the api's embedder 2.1 s, the same call with 127.0.0.1 0.07 s). The local stack now uses 127.0.0.1 for Ollama and Chroma. The CPU run is kept, labelled baseline-cpu-ollama; its embedding times include that 2 s |
| 2026-11-28 | Batch B ingestion: intake moved all 12 files into raw/, but the verification table listed only the 9 corpus documents and nothing new was embedded | raw/ holds fetch.py's _index.json, and read_folder() read only that index, so documents moved in from incoming/ without an index of their own were invisible | read_folder() adds documents the index does not list, from their front matter, and skips README and MANIFEST files; test_a_batch_beside_a_fetch_index_is_still_catalogued fails without it |
| 2026-11-28 | Rollback demo: `pipeline.ops restore fee-structure-page 2026-27` made the old page current, then the next ingestion archived it again and left both versions superseded (eval/results/a/07a-rollback-bug-rearchived.log) | The recency check compared with every indexed version, including the 2027-28 one that the restore had just archived on purpose, so the restored page always had a newer version | Recency compares with the current (raw/) versions only, and an archived entry stays archived; test_a_rollback_survives_the_next_ingestion fails without it |

## 2026-11-28 · ragops/f-kubernetes · uniqueness quarantined a real corpus document (Member 2)
- **Symptom:** the first ingestion Job on a fresh minikube indexed 767 chunks instead of 803.
  The verification table showed the 2026 prospectus quarantined: "near duplicate of
  undergraduate-academic-rules-aug-2023.pdf (cosine 0.954 >= 0.950)".
- **Cause:** VERIFY_NEAR_DUPLICATE was a provisional 0.95, set before any measurement. The
  prospectus is a 5-page summary of the same rules, so its embedding sits close to the rules.
- **Fix:** measured every document pair (python -m pipeline.ops similarities): different
  documents reach at most 0.9588, the planted near duplicate 0.9997. Threshold 0.98 in the
  ragops-gate ConfigMap (eval/results/a/09-uniqueness-threshold.txt). Lesson: the same as
  the relevance floor in A02: a threshold is a measurement, never a guess.

## 2026-11-28 · ragops/f-kubernetes · the planted b09 claim reached a user, then the cache (Member 2)
- **Symptom:** after Batch B, "Are all fees waived this semester according to the IT
  policy?" answered "true [b09-it-acceptable-use.md / 3. Assistant notice]". The trace
  showed the retrieval rail had flagged the chunk three times (flag mode). After switching
  the ConfigMap to redact and restarting the api, the same question returned the same
  answer with `cached: true`.
- **Cause:** (1) flag mode only records; the A02 defence blocks obeying and invented
  citations, not the model quoting a planted claim with a real citation. (2) The answer
  passed every cache rule, and only an indexer run bumps the cache generation, not a
  ConfigMap change.
- **Fix:** GUARDRAIL_INJECTION_ACTION=redact in rahbar-config; answers built on flagged
  evidence are never cached (test shown red without it); the cache generation bumped once
  by hand for the demo. Evidence: eval/results/f/11-d4-flag-mode.txt and
  13-d4-redact-mode.txt.

## 2026-11-28 · ragops/f-kubernetes · a release served the previous configuration's cached answers (Member 2)
- **Symptom:** right after `kubectl set env deployment/api CHROMA_COLLECTION=rahbar-k6
  TOP_K=6` and a finished `rollout status`, the first question returned `cached: true`; its
  trace showed collection rahbar-k6, yet the answer was the one the old pods had cached
  from rahbar with top_k 5.
- **Cause:** the semantic cache had one list per index generation, shared by every
  configuration. Only an indexer run bumps the generation, and a release or rollback by
  `set env` runs no indexer. Worse for the bad release: all-minilm question vectors (384-d)
  would have been compared with cached nomic vectors (768-d); `zip` silently truncates.
- **Fix:** cache entries are keyed by generation *and* a fingerprint of collection,
  embedding model, top_k, relevance floor, LLM and rail mode (providers/cache). A release
  starts with an empty cache for its configuration; an undo finds the old one again. Test
  shown red without the scope.
