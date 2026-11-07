# AI usage

| Tool | What it wrote or shaped | What we changed afterwards, and why |
| --- | --- | --- |
| Claude Code | Dev 1 pipeline work; each change is listed in the logs below | Recorded per entry below |

## Skill log

## 2026-11-07 · feat/s2-corpus
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D1-P1 task list: pick nine documents (§2); fetch them and write MANIFEST (§2); verify SHA-256 hashes (§2); prove scans with font lists (§2); write CORPUS rows (§2); record superseded flags (§3.1).
- **I changed:** accepted as-is.

## 2026-11-07 · feat/s5-eval-harness
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D1-P2 task list: write golden.yaml from the documents (§5.1); implement recall_at_k (§5.2); implement citation_validity (§5.3); implement summarise by type (§5.2); implement gate with exit codes (§5.4); run against make dev with stubs and commit the fixture baseline (§5.4).
- **I changed:** accepted as-is.

## 2026-11-07 · feat/s3.1-indexer
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D1-P3 task list: extract PDF, HTML and Markdown with OCR for textless pages (§3.1); clean headers, footers and contents (§3.1); chunk by section, paragraph and sentence with overlap (§3.1); embed in batches through Ollama (§3.1); store with upsert and pruning (§3.1, §4.4); invalidate the cache last (§3.3); test each stage on fixtures (§3.1); fetch the corpus into the Job with verification (§2).
- **I changed:** accepted as-is.

- **Tool:** Claude Code + `ponytail`
- **Shaped / Wrote:** OCR engine (D12), PDF extraction library (D13), chunk unit (D14), re-index strategy (D15).
- **I changed:** accepted as-is. pdf2image was dropped from indexer/requirements.txt because nothing uses it.

## 2026-11-07 · feat/s3.4-grounded-generation
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D1-P4 task list: retrieve read-only from Chroma with the superseded filter (§3.2); abstain below the relevance floor (§3.4); define the provider interface with Ollama and hosted (§3.5); build the augmented prompt (§3.2); validate, retry once, fall back (§3.4); drop unretrieved citations (§3.4); write the never-skipped tests (§3.4).
- **I changed:** accepted as-is.

- **Tool:** Claude Code + `ponytail`
- **Shaped / Wrote:** older-version detection (D17), provider interface (D18).
- **I changed:** accepted as-is. The relevance floor default is recorded as ASSUMED (D19) until it is measured.

## 2026-11-07 · feat/s3.2-conversation-history
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D1-P4b task list: write ADR 0002 before code (§3.2); store turns in localStorage with a reset (§3.2); cap and validate history and summary (§3.2); detect follow-ups with a measured false-positive check (§3.2); rewrite follow-ups for retrieval (§3.2); put conversation context before the evidence (§3.2); write the summary through the provider (§3.2); count follow-ups and summary failures (§4.8); write the tests (§3.4).
- **I changed:** accepted as-is.

- **Tool:** Claude Code + `ponytail`
- **Shaped / Wrote:** ADR 0002 options (server sessions, sticky sessions, full transcript, LLM rewrite) and the follow-up detector (D20).
- **I changed:** accepted as-is.

## 2026-11-07 · feat/s3.3-semantic-cache
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D1-P5 task list: build the Redis cache module with a threshold from config (§3.3); respect the generation key the indexer bumps (§3.3); never cache follow-ups, abstentions, out-of-scope or failed answers (§3.3); degrade Redis errors to a miss (§3.3); report Chroma and Redis on /readyz (§4.3); write ADR 0003 (§3.3); write the tests (§3.3).
- **I changed:** accepted as-is.

- **Tool:** Claude Code + `ponytail`
- **Shaped / Wrote:** ADR 0003 alternatives (second Chroma collection, per-pod cache, redis-stack vector index) and the linear-scan ceiling.
- **I changed:** accepted as-is.

## 2026-11-07 · feat/s4.8-observability
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D1-P6 task list: log one JSON line per request with top_k, chunk ids, scores and abstention (§4.8); log the raw prompt at DEBUG only (§4.8); add retrieval and generation latency histograms (§4.8); add the cache hit ratio, abstention and fallback counters (§4.8); add tokens in and out per request (§4.8); test the line and the metric names (§4.8).
- **I changed:** accepted as-is.

## 2026-11-07 · feat/s5.2-measure-and-tune
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D1-P7 task list: install Ollama with nomic-embed-text and llama3.2:3b (user approved) (§3.5); measure at least three chunk configs for recall@5 (§3.1); choose the relevance floor from the abstain and answerable scores (§3.4); choose the lowest cache threshold with zero false hits (§3.3); write the real and fixture baselines (§5.4); hand the ConfigMap values over with their sources (§4.1).
- **I changed:** accepted as-is. Measured on this laptop (local chromadb 1.0.12 and Ollama on the GPU), not on minikube, because the cluster is Dev 2's and not up yet; the values carry over because the models and the code are the same.

## 2026-11-07 · feat/s5.5-failure-analysis
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D1-P8 task list: break and measure stages A, B, C and E one at a time (§5.5); write FAILURE-ANALYSIS.md with symptom, diagnosis, stage and remedy (§5.5); finish the PIPELINE.md stage report (§3.1); answer engineering notes Q5 and Q6 with file:line references (§7).
- **I changed:** accepted as-is. Stage B's expected recall drop did not happen, and the write-up says so rather than forcing the narrative.

## 2026-11-07 · fix/s3.4-audit-gaps
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** audit fix list: strip whitespace before the 3-500 check (§3.2); keep each request under the Ingress timeout (§3.4); move SERVE_UI_DIR and HOSTNAME into the config modules (CLAUDE.md §3); refuse TEMPERATURE outside 0-0.3 (§3.4); delete the merged branches' handover file (AGENTS.md).
- **I changed:** accepted as-is. Gap 5 (cache ignores the old-version flag) was left out because the user chose 1-4 and 6; it is measured as safe at 0.96.

## 2026-11-07 · fix/s3.3-cache-old-versions
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** gap 5 task list: decide the old-version flag before the cache check (§3.2); skip the lookup for old-version questions (§3.3); never store their answers (§3.3); test that a same-worded old-version question neither hits nor is stored (§3.3).
- **I changed:** accepted as-is.

## 2026-11-07 · feat/s3.4-brief-gaps
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** brief-audit task list: document chunk count and metadata schema (§3.1); require inline [source / section] markers and check them against what was retrieved (§3.4); index the planted injection through the real pipeline in a test (§3.4); report answer correctness outside the gate (§5.3); draft Dev 1 input for README and ADRs 0001 and 0004 (§2, §3.5, §4.2).
- **I changed:** accepted as-is.

## 2026-11-07 · feat/s4.7-container-images
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D2-P2 task list: write api/Dockerfile on pinned python:3.12.11-slim with a non-root USER (§4.7); write indexer/Dockerfile with tesseract-ocr, fetch.py, sources.yaml, MANIFEST.md and the fixtures (§3.1, §6); write ui/Dockerfile on pinned nginx-unprivileged (§4.7); exclude .git, caches, venvs and corpus/raw from every build context (§6); build all three from `make images` (§6); run each image with a read-only root filesystem and an emptyDir-style /tmp (§4.7).
- **I changed:** accepted as-is.

- **Tool:** Claude Code + `ponytail`
- **Shaped / Wrote:** how the indexer image gets corpus/fetch.py and the manifest: build context = repository root with `-f indexer/Dockerfile` and an allowlist `.dockerignore` at the root (chosen); rejected BuildKit named contexts (`--build-context corpus=corpus`: two extra contexts for corpus/ and eval/fixtures, and corpus/raw would be sent unless each has its own ignore file); rejected copying corpus files into indexer/ in the Makefile (generated copies that drift from the committed MANIFEST).
- **I changed:** accepted as-is. The checker's `indexer/.dockerignore` line stays red because it assumes context `indexer/`; the root file does that job.

## 2026-11-07 · feat/s4.1-k8s-base
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D2-P3 task list: start minikube with Calico, metrics-server and ingress (§4.1); write the namespace, one ServiceAccount per workload, the ConfigMap and the placeholder Secret (§4.1, §4.7); write the chroma StatefulSet and the redis Deployment with a PVC, both ClusterIP (§4.1); write the api Deployment with the §4.3 probes, maxSurge 1, maxUnavailable 0 and a preStop sleep (§4.3, §4.6); write the indexer Job and the weekly reindex CronJob (§4.2); write the Ingress and the HPA (§4.1); write the dev and prod overlays (§6); run the indexer, ask through the Ingress, delete an api pod (§1.3).
- **I changed:** started from the real configuration (RETRIEVER=chroma, LLM_PROVIDER=ollama-host) instead of the stubs, because Dev 1's pipeline was already merged; the stub-first order in STARTER.md exists for when it is not.

- **Tool:** Claude Code + `ponytail`
- **Shaped / Wrote:** what the prod overlay commits as the image tag: a fixed `set-by-cd` value that cd.yml replaces with `${{ github.sha }}` (chosen); rejected committing a real SHA after every merge (a bot commit per deploy, and the tag would name the commit before itself); rejected one overlay per environment variable (`envsubst` on the YAML: a second templating tool beside Kustomize).
- **I changed:** accepted as-is.

## 2026-11-07 · feat/s4.7-network-policy
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D2-P4 task list: deny all ingress and egress in rahbar (§4.7); allow DNS to kube-dns on 53 UDP and TCP (§4.7); allow ui from ingress-nginx, api from ingress-nginx and ui (§4.7); allow chroma and redis from api and indexer only (§4.7); allow api and indexer egress to the Ollama host ipBlock and the indexer to nu.edu.pk on 443 (§4.7, Q4); prove ui to chroma fails and api to chroma works, into docs/evidence/ (§4.7).
- **I changed:** accepted as-is. Pod security (non-root, read-only root, capabilities, no token) was already in the D2-P3 manifests, so this phase is the NetworkPolicy alone.

- **Tool:** Claude Code + `ponytail`
- **Shaped / Wrote:** how the indexer reaches nu.edu.pk: an ipBlock for its one address 203.124.44.78/32 on 443 (chosen); rejected 0.0.0.0/0 on 443 (opens the whole internet to the only Chroma writer); rejected an egress proxy or Calico's DNS-name policies (a new component, or a Calico-only API that kind's CNI in CI would not apply).
- **I changed:** accepted as-is. If the university moves the site, the Job fails at the fetch step with a timeout, which is loud, and the fix is one CIDR.

## 2026-11-07 · feat/s4.4-embed-pin
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** swap-task list (Dev 2 into the RAG area): read the indexer's pin from the collection metadata (§4.4); compare model name and vector dimension with the api's EMBED_MODEL and embedder (§4.4); fail /readyz with 503 naming both values (§4.3, §4.4); log the conflict once, not on every probe (§4.8); test mismatch, match, dimension and recovery (§4.4); demonstrate on minikube by changing the ConfigMap without re-indexing (§4.4).
- **I changed:** accepted as-is.

- **Tool:** Claude Code + `ponytail`
- **Shaped / Wrote:** where the pin is checked: once at startup and again on every /readyz (chosen, since a re-index can change the collection while the pod runs); rejected startup only (a pod started before a model change keeps serving the wrong index), and rejected checking inside every /api/ask (a per-question Chroma metadata read, and the user would get a fallback instead of the pod leaving the Service). How the api learns its own dimension: one probe embedding at startup and the length of every later vector (chosen); rejected a dimension in the ConfigMap (a second, hand-typed copy of the pin, which CLAUDE.md §1.4 forbids).
- **I changed:** accepted as-is.

## 2026-11-07 · feat/s6-ci
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D2-P6 task list: run ruff and mypy (§6); run pytest with coverage at least 60 % on the api app package, stubs only (§6); run kustomize build for both overlays through kubeconform -strict and refuse :latest (§6); build the three images without pushing (§6); scan them with Trivy and fail on fixable HIGH or CRITICAL (§6); set a least-privilege permissions block (§6).
- **I changed:** left the e2e-eval job out: it is Dev 1's swap task, so it comes in a Dev 1 PR. Gated build on lint, test and manifests, so the checker does not read an image build as an ungated publish.

- **Tool:** Claude Code + `ponytail`
- **Shaped / Wrote:** how the scan gets the image: build once per image, export it as an artifact, scan in a needs: build job (chosen); rejected building again inside the scan job (two builds that can differ), and rejected pushing to a registry from CI to scan there (nothing may push from a PR, §6).
- **I changed:** accepted as-is.

## 2026-11-07 · feat/s6-ci (cd.yml)
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D2-P7 task list: run the tests again on the main commit (§6); log in to Docker Hub with an access token from GitHub Secrets (§6); push the three images tagged with the commit SHA, needs: test (§6); create an ephemeral kind cluster, needs: build-push (§6); deploy that SHA and wait on rollout status (§6); smoke-test through the Ingress (§6).
- **I changed:** the deploy runs the prod images with the stub provider and the dummy index (k8s/overlays/ci), because kind has no Ollama; the real pipeline is proven on minikube instead (docs/evidence/cluster-proof.txt).

## 2026-11-07 · feat/s4.5-resources
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D2-P5 task list: sample kubectl top pods during a real index and a 40-question burst (§4.5); set requests and limits on every container from the peaks with a stated margin (§4.5); commit the raw output (§4.5); capture the HPA reading a real value (§4.5); show 3 api endpoints without touching the Service (§4.6); set image, watch the rollout, undo it (§4.6). The embedding-pin demonstration is already in docs/evidence/embedding-pin-demo.txt (§4.4).
- **I changed:** accepted as-is. My first summary compared the samples as strings and under-read the indexer's peak as 77m and 703Mi; the real peak is 1659m and 1159Mi, which would have put the indexer at 75 % of its provisional limit.

## 2026-11-07 · feat/s7-platform-docs
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D2-P9 task list: write ADR 0001 (indexer as a Job) from the measured run (§4.2); write ADR 0004 (provider and data governance) from Dev 1's facts (§3.5); write ARCHITECTURE.md with the diagram and why Chroma is a StatefulSet (§4.1); replace README.md with the summary, the clean-clone apply order, make secret, the corpus and the embedding route (§7, §10); answer engineering notes Q1-Q4 with file:line references (§7); delete Dev 1's handover file once used (AGENTS.md).
- **I changed:** answered Q2 and Q4 from new measurements rather than reasoning alone: the probes as shipped and swapped with Chroma down for 90 s (docs/evidence/probes-chroma-down.txt), and the indexer at a 768Mi limit (docs/evidence/indexer-oom-137.txt). Removed an ARCHITECTURE.md claim about deleting chroma-0 that had not been tested, and replaced it with the scale-to-0 result that was.

## Task log

- 2026-11-07 · feat/s2-corpus · Seeded DECISIONS.md, failure-log.md and the handover folder so Dev 1 work can record decisions (D2-P1 had not landed); chose the corpus in corpus/sources.yaml (§2).
- 2026-11-07 · feat/s2-corpus · Ran fetch.py for all nine documents, confirmed `--verify` passes 9 of 9, committed corpus/MANIFEST.md (§2).
- 2026-11-07 · feat/s2-corpus · Wrote docs/CORPUS.md: one row per §2 property with document, page, evidence and failure mode.
- 2026-11-07 · feat/s2-corpus · Confirmed _index.json flags (only the 2023 rules are superseded), documented how the flag is set, added a discover() test (§3.1).
- 2026-11-07 · feat/s5-eval-harness · Wrote eval/golden.yaml: 20 questions (10 ordinary, 2 version, 3 exact, 3 abstain, 2 injection), sections taken from the document bodies (§5.1).
- 2026-11-07 · feat/s5-eval-harness · Implemented recall_at_k, citation_validity, summarise and gate in eval/run_eval.py, with eval/test_run_eval.py; `make test` runs it and `make eval-fixtures` uses its own baseline file (§5.2-§5.4).
- 2026-11-07 · feat/s5-eval-harness · Ran the fixture eval end to end against stubs (exit 1, as expected), recorded the evaluation method in PIPELINE.md; fixture baseline deferred until the real retriever runs (§5.4).
- 2026-11-07 · feat/s3.1-indexer · Implemented extract: PDF cropped to the page box, headings by font size, tesseract OCR for textless pages (41 pages in the corpus), HTML tables as rows; tests in indexer/tests/test_extract.py (§3.1).
- 2026-11-07 · feat/s3.1-indexer · Implemented clean: running headers and footers, page numbers and contents entries removed, clause numbers kept; tests in indexer/tests/test_clean.py (§3.1).
- 2026-11-07 · feat/s3.1-indexer · Implemented chunk: sections, then paragraphs, then sentences or table rows, word overlap inside a section, heading at the top of every chunk; 550 chunks, storage amplification 1.009 at 400/50 on the real corpus; tests in indexer/tests/test_chunk.py (§3.1).
- 2026-11-07 · feat/s3.1-indexer · Implemented embed: batched POST /api/embed with EMBED_MODEL from config, fails the run on an HTTP error, a missing vector or mixed lengths; tests use httpx.MockTransport (§3.1).
- 2026-11-07 · feat/s3.1-indexer · Implemented store: the only Chroma writer, upsert then prune, rebuild on a pin change, writes embed_model and dimension; tested with a fake client and by hand against chromadb 1.0.12 (§3.1, §4.4).
- 2026-11-07 · feat/s3.1-indexer · Added cache invalidation as the last step of every run (Redis INCR on rahbar:cache:generation, the Job fails if Redis is down), storage amplification in the run log, and an end-to-end run test on the fixtures (§3.3, §3.1).
- 2026-11-07 · feat/s3.1-indexer · Corpus delivery (Q4): fetch.py --out DIR for the Job's emptyDir and --verify --out DIR against the committed MANIFEST; 2023 rules URL moved to https; PIPELINE.md extraction, cleaning, chunking and embedding sections (§2, §3.1).
- 2026-11-07 · feat/s3.4-grounded-generation · ChromaRetriever: question embedded with EMBED_MODEL, top-k, superseded excluded unless asked for, cosine similarity scores, never writes (§3.2).
- 2026-11-07 · feat/s3.4-grounded-generation · Providers (stub, ollama with format=schema, hosted with response_format), augmented prompt with delimited evidence, relevance-floor abstention, one retry then canned answer, citation check, and 23 stub-only tests each shown to fail with its guard removed (§3.4, §3.5).
- 2026-11-07 · feat/s3.2-conversation-history · Wrote docs/adr/0002-conversation-history-in-browser.md: contract change, window and summary protocol, follow-up rule, history as untrusted data (§3.2).
- 2026-11-07 · feat/s3.2-conversation-history · API side of ADR 0002: capped history and summary in AskRequest (422 past HISTORY_TURNS), follow-up detection and rewrite, conversation block before the evidence, summary fold with failure fallback, follow-up and summary-failure counters, 11 tests (§3.2, §4.8).
- 2026-11-07 · feat/s3.2-conversation-history · ui/index.html keeps the conversation in localStorage (question and shown answer only, window from history_turns, summary from the API), sanitises the stored turns, adds a New conversation reset, and works when storage is blocked. Script syntax checked with node; not yet clicked through in a browser (§3.2).
- 2026-11-07 · feat/s3.2-conversation-history · Added follow-up questions q21-q22 (type followup, with history) to eval/golden.yaml; run_eval.py sends their history and keeps them out of the gated numbers; checked end to end against make dev (follow-up counter reads 2) (§5.1, §3.2).
- 2026-11-07 · feat/s3.3-semantic-cache · Wrote docs/adr/0003-semantic-cache-store.md: Redis rather than a second Chroma collection, with the rejected alternatives (§3.3).
- 2026-11-07 · feat/s3.3-semantic-cache · Semantic cache in api/app/providers/cache/ (cosine over the current generation, CACHE_THRESHOLD from config, CACHE=redis|none), wired into the query path with the never-cache rules and a cached flag for the UI chip; /readyz reports Chroma (non-empty) and Redis with 503 naming the failure; 12 tests, each guard shown to fail when removed (§3.3, §4.3).
- 2026-11-07 · feat/s4.8-observability · Added rahbar_retrieval_seconds, rahbar_generation_seconds, rahbar_tokens_per_request{direction}, rahbar_abstentions_total, rahbar_fallbacks_total{reason} and rahbar_cache_hit_ratio, with bounded labels only; the raw prompt is logged at DEBUG; tests check the request line and every metric name (§4.8).
- 2026-11-07 · feat/s4.8-observability · Pinned pytest-cov for the CI coverage gate; wrote docs/handover/HANDOVER-feat-s4.8-observability.md (branch stack, blocked items, notes for Dev 2) (§6).
- 2026-11-07 · feat/s5.2-measure-and-tune · The first real llama3.2:3b run showed the model miscopying citation fields and saying answered_from_context=false next to a correct answer: evidence now ends with a literal "cite as" JSON line, and a not-from-context reply always shows the standard decline; invalid outputs went from 4 to 0 (§3.4).
- 2026-11-07 · feat/s5.2-measure-and-tune · Measured six (CHUNK_SIZE, CHUNK_OVERLAP) configs on the real corpus and shipped 150/30 (recall@5 0.938); table in PIPELINE.md, raw numbers in docs/evidence/tuning-chunks.json (§3.1).
- 2026-11-07 · feat/s5.2-measure-and-tune · Chose RELEVANCE_FLOOR 0.65 from the abstain and answerable score gap, and CACHE_THRESHOLD 0.96 as the lowest with zero false hits on eval/cache_pairs.yaml (0.95 failed on 15 against 30 days); evidence in docs/evidence/relevance-floor.txt and cache-threshold.txt (§3.4, §3.3).
- 2026-11-07 · feat/s5.2-measure-and-tune · First baselines: eval/results.json and eval/baseline.json from llama3.2:3b on the real index (recall@5 0.938, citation validity 1.00, abstention 1.00), and eval/fixtures/baseline.fixture.json taken the way CI runs (stub LLM, real embeddings) (§5.4).
- 2026-11-07 · feat/s5.5-failure-analysis · FAILURE-ANALYSIS.md: no-OCR index (23 chunks lost, a wrong document clears the floor at 0.680), 100/0 chunks (no recall drop, explained by heading-prefixed chunks), top_k 1 (0.938 to 0.656) and an api-only model change (768 against 384 dimensions, every answer canned), and no superseded filter (2023 outranks 2026 on q11 by 0.001) (§5.5).
- 2026-11-07 · feat/s5.5-failure-analysis · ENGINEERING-NOTES Q5 (exact-term recall 0.667 from q13 "clause 1.21"; hybrid BM25 as the lecture fix) and Q6 (api-only model change measured: canned answers while /readyz stays ready; what the pin guard changes) (§7).
- 2026-11-07 · feat/s5.5-failure-analysis · Pre-PR hardening review of all nine branches (findings and WONTFIX reasons are in each PR body). Fixed the one real gap it found: a listed document that yields zero chunks now fails the indexer run (indexer/pipeline/run.py), with a test (§6, §3.1).
- 2026-11-07 · fix/s3.4-audit-gaps · Whitespace-only questions are now a 422, TEMPERATURE outside 0-0.3 refuses startup, and SERVE_UI_DIR and HOSTNAME are read only in the config modules; tests in api/tests/test_validation.py, each shown to fail without its fix (§3.2, §3.4).
- 2026-11-07 · fix/s3.4-audit-gaps · REQUEST_BUDGET_SECONDS (50) caps each /api/ask below the nginx Ingress 60 s read timeout: each model call gets only the time left, the retry and the summary are skipped when under 1 s remains; tests in api/tests/test_budget.py with a fake clock (§3.4).
- 2026-11-07 · fix/s3.4-audit-gaps · Deleted the handover file of the merged Dev 1 stack (AGENTS.md: delete at merge) after moving the ConfigMap values, the indexer image and the egress needs into docs/PIPELINE.md, "Configuration for the cluster" (§4.1).
- 2026-11-07 · fix/s3.3-cache-old-versions · Questions that ask about an older version now bypass the semantic cache in both directions, like follow-ups, so a current answer is never served for "the 2023 rules" or the other way round (api/app/services/answer.py, test in api/tests/test_cache.py) (§3.3).
- 2026-11-07 · feat/s3.4-brief-gaps · PIPELINE.md gains a Store section: 803 chunks by document, the per-chunk metadata schema and the collection metadata, plus how the api checks the pin today (§3.1).
- 2026-11-07 · feat/s3.4-brief-gaps · Inline [source / section] markers: the prompt shows each passage's marker, check_markers removes any naming nothing retrieved and adds the checked citations' markers when missing; real run kept citation validity at 1.00 (§3.4).
- 2026-11-07 · feat/s3.4-brief-gaps · run_eval.py reports answer_correctness from the golden expect strings (numbers must all appear, else a case-insensitive substring), outside the gate; eval/results.json re-run with llama3.2:3b gives 0.688, recall@5 0.938, citation validity 1.00; baseline unchanged (§5.3).
- 2026-11-07 · feat/s3.4-brief-gaps · eval/test_poisoned_chunk.py: the fixture's planted instruction goes through the real extract, clean, chunk and store code, is retrieved, and an obedient fake model still cannot get "attendance is optional" or its own citation to the user; shown to fail with the citation check removed (§3.4).
- 2026-11-07 · feat/s3.4-brief-gaps · docs/handover/dev1-input-for-dev2.md: README paragraphs (corpus via MANIFEST and fetch.py, embeddings through the same Ollama host, a no-cluster run), and the indexer facts for ADR 0001 and the data-flow facts for ADR 0004, each traced to a file (§2, §3.5, §4.2).
- 2026-11-07 · docs/s6-account-split · CLAUDE.md §1.23 and AGENTS.md name the account for each dev's work: Dev 1 as Nu-AbdulRehman, Dev 2 as MTH99910, for commits, PRs and reviews, each reviewing the other's PRs (§6).
- 2026-11-07 · feat/s4.7-container-images · api, indexer and ui Dockerfiles on pinned bases, non-root numeric USER, exec-form CMD; indexer built from the repository root with an allowlist .dockerignore so it carries fetch.py, MANIFEST and the fixtures; all three verified read-only with only /tmp writable (§4.7, §6).
- 2026-11-07 · feat/s4.1-k8s-base · k8s/base (namespace, ServiceAccounts, ConfigMap, placeholder Secret, chroma StatefulSet, redis Deployment+PVC, api with the §4.3 probes and HPA, ui, indexer Job and CronJob, Ingress) and dev/prod overlays; real index built in-cluster (803 chunks), answers through the Ingress, 20/20 requests 200 while an api pod was deleted (docs/evidence/cluster-proof.txt) (§4.1-§4.3, §4.6).
- 2026-11-07 · feat/s4.1-k8s-base · ChromaRetriever connects on first use, so a Chroma that is down at boot leaves the api alive and not ready instead of crash-looping; enableServiceLinks: false on every pod after the CHROMA_PORT service-link crash (§4.3).
- 2026-11-07 · feat/s4.7-network-policy · k8s/base/networkpolicy.yaml: deny by default, then DNS, ui, api, chroma, redis and indexer rules; ui cannot reach chroma or redis, api can, the internet is closed except nu.edu.pk for the indexer; a full re-index and cited answers still work (docs/evidence/networkpolicy-proof.txt) (§4.7).
- 2026-11-07 · feat/s4.4-embed-pin · Embedding-pin guard (swap task): services/pin.py compares the collection's embed_model and dimension with the api's EMBED_MODEL and embedder; /readyz returns 503 naming both and logs the conflict once; 11 tests, shown red with the readyz check removed; minikube demo in docs/evidence/embedding-pin-demo.txt (§4.3, §4.4).
- 2026-11-07 · feat/s6-ci · Newer pinned bases (python:3.12.16-slim, nginx-unprivileged:1.30.6-alpine) plus OS upgrades: Trivy finds no fixable HIGH or CRITICAL OS package; Python pins in api/ and indexer/ still need Dev 1's bump (§6).
- 2026-11-07 · feat/s6-ci · .github/workflows/ci.yml: lint, test (coverage at least 60 %), manifests (kubeconform -strict on dev and prod, no :latest), build (no push) and Trivy scan, read-only permissions (§6).
- 2026-11-07 · feat/s6-ci · .github/workflows/cd.yml: test, build-push by commit SHA to docker.io/mth99910 (needs: test), deploy to kind with ingress-nginx and a smoke test through the Ingress (needs: build-push); k8s/overlays/ci runs it with stubs and the dummy index (§6).
- 2026-11-07 · feat/s4.5-resources · Requests and limits on every container from kubectl top peaks (indexer 1659m/1159Mi, api 186m/129Mi, chroma 26m/107Mi), HPA at 4-6 % of 70 %, 3 api endpoints, rollout to v2 and undo (docs/evidence/kubectl-top.txt, rollout-and-endpoints.txt) (§4.5, §4.6).
- 2026-11-07 · feat/s7-platform-docs · ADR 0001 and ADR 0004, docs/ARCHITECTURE.md, the new README.md (apply order, make secret, corpus, models, API table) and engineering notes Q1-Q4, with two new measurements: probes swapped under a 90 s Chroma outage (all three pods restarted) and the indexer OOM-killed with exit 137 at 768Mi (§4.2, §4.3, §4.5, §7, §10).
