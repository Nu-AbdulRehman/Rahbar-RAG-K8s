# Rahbar RAG Implementation Plan

Nov 6, 2026 · the user

## Overview

Two developers, each driven by an AI agent, turn the RAHBAR starter kit into a grounded RAG service on Kubernetes: Dev 1 builds the RAG pipeline and evaluation, Dev 2 builds the platform and CI/CD, and each does one real task in the other's area. The plan lists phases and tasks with the rules each task must obey; code-level design is left to the agent.

**What "done" means (brief §1.3).** A stranger clones the repo, starts minikube, applies the manifests in the README's order, runs the indexing Job, and asks a question through the Ingress. They get a cited, grounded answer. A question the corpus does not cover is declined. Deleting a pod breaks nothing.

**Source of truth, highest first:** the brief (problem\_statement.pdf, cited as §N.N) > STARTER.md (contracts, env vars, Makefile targets) > ADRs and docs/decisions/DECISIONS.md > the required docs > CLAUDE.md / AGENTS.md examples. If code and the brief disagree, the code is the bug.

**Order of work (STARTER.md).** The platform is built first around the stubs (RETRIEVER=stub, LLM\_PROVIDER=stub, indexer --dummy, EMBED\_MODEL=dummy-768). The real pipeline replaces the stubs in parallel and is switched on through the ConfigMap. Neither dev waits on the other to start.

**Out of scope unless the user says otherwise:** ollama-incluster (bonus) and hybrid BM25 retrieval are deferred until the project is complete (Q6); no UI build step.

## Global rules and decisions

Every task below inherits these. CLAUDE.md §1 (the 23 HARD rules) and the §2 deduction ledger are binding on both agents; they are summarised here, not replaced.

### Decisions already made

These seed docs/decisions/DECISIONS.md as resolved rows in the bootstrap phase. No agent re-decides them.

| # | Decision | Rule it implies |
| --- | --- | --- |
| D1 | LLM provider is ollama-host (llama3.2:3b on the laptop, reached at host.minikube.internal:11434) | hosted is a working one-file swap; stub is used in every test and CI unit run |
| D2 | Embeddings are nomic-embed-text through the same Ollama host | EMBED\_MODEL is one ConfigMap key read by api and indexer; stated in README (§3.5) |
| D3 | Semantic cache is Redis | Deployment + PVC, ClusterIP only; defended in an ADR against a second Chroma collection (§3.3) |
| D4 | Local cluster is minikube with Calico, metrics-server and ingress | make cluster per STARTER.md; namespace rahbar; host rahbar.local |
| D5 | CI clusters are kind | e2e-eval indexes eval/fixtures and gates on golden.fixture.yaml with its own fixture baseline; never mixed with the real baseline |
| D6 | Docs are a small set | README, ARCHITECTURE, CORPUS, PIPELINE, FAILURE-ANALYSIS, ENGINEERING-NOTES, AI-USAGE, failure-log, ADRs 0001–0004, evidence/, plus docs/decisions/DECISIONS.md |
| D7 | Ownership: Dev 1 = RAG pipeline and eval; Dev 2 = Dockerfiles, k8s, workflows, Makefile additions | Each dev does exactly one real swap task (see The swap) |
| D8 | Git identity is the user's own account only | No Co-Authored-By, Claude-Session or "Generated with Claude Code" lines in commits, PRs or comments; AI use disclosed only in docs/AI-USAGE.md |
| D9 | Images pinned: python:3.12.x-slim, chromadb/chroma:1.0.12 (matches chromadb-client==1.0.12), redis:7.x, nginxinc/nginx-unprivileged:\<ver> | Our images tagged and deployed by commit SHA, never :latest |

**D10 · Conversation history lives in the browser.** The UI keeps the last N turns verbatim plus a summary of older ones and sends both with each question; the API uses them for follow-up detection and as prompt context, and stores nothing. Contract change covered by an ADR (D1-P4b).

### Rules every task follows

- **Git flow.** feature branch → dev → main. main is protected: PR, green CI, one approval. Branch names \<type>/s\<section>-\<desc>; Conventional Commits citing §N.N. The first PR names the corpus.
- **Reviews.** The partner reviews every PR with a substantive comment. Before opening a PR, the agent runs the pre-PR hardening review: at least 3 file:line findings on the diff, each fixed or marked WONTFIX.
- **Skills.** caveman at the start of every phase (stripped, §-tagged task list); ponytail at every design fork (≥2 rejected alternatives with reasons); grilling whenever a user answer is needed. Every invocation and every completed task is logged in docs/AI-USAGE.md as it happens.
- **Config.** Only api/app/config.py and indexer/pipeline/config.py read the environment. Every tunable lives in the ConfigMap with a comment saying where its value came from. No tunable is a constant in code.
- **Numbers are measured.** Chunk size and overlap, relevance floor, cache threshold and every resource request or limit need a committed measurement table or kubectl top output. A number without evidence scores zero.
- **Tests.** make test, make lint (ruff, mypy) and make check pass before every commit. API coverage stays ≥ 60 % with stubs only. No sleep, real network or real model in unit tests. A test is done only after it is shown to fail without the implementation.
- **Failures.** Anything that breaks is appended to docs/failure-log.md at the time it happens (feeds engineering note Q7).
- **Handover.** A session ending on an unmerged branch writes docs/handover/HANDOVER-\<branch>.md; a session touching code it did not write reads it first.
- **Done check.** Before reporting a task done, the agent walks the CLAUDE.md §7 checklist.

## Architecture and repository layout

Two paths never share a process: the indexer Job is the only writer to Chroma, and the API only reads it (§3). Everything runs in namespace rahbar.

| Component | Kind | Owner | Key rules |
| --- | --- | --- | --- |
| api | Deployment, 3 replicas, HPA 3–8 | Dev 1 code, Dev 2 manifest | Port 8000; startup/liveness on /healthz, readiness on /readyz; maxSurge 1, maxUnavailable 0, preStop sleep |
| ui | Deployment, ≥1 replica | Dev 2 | Port 8080; non-root, read-only root fs, emptyDir at /tmp |
| chroma | StatefulSet, 1 replica, volumeClaimTemplates | Dev 2 | Port 8000, data in /data, heartbeat /api/v2/heartbeat; reason for StatefulSet in ARCHITECTURE.md |
| redis | Deployment + PVC | Dev 2 manifest, Dev 1 cache code | Port 6379; reachable from api and indexer only |
| indexer | Job (restartPolicy OnFailure, backoffLimit set) + weekly CronJob reindex, same image and args | Dev 1 code, Dev 2 manifests | Only Chroma writer; writes model name and dimension into collection metadata; invalidates cache as last step |
| Ingress | nginx ingress, host rahbar.local | Dev 2 | / → ui, /api → api |
| ConfigMap / Secret | rahbar-config, rahbar-secret | Dev 2 objects, Dev 1 values | Secret created from CLI only; placeholder never in kustomization.yaml |
| NetworkPolicy | deny by default + allow list | Dev 2 | ui from ingress; api from ui and ingress; chroma from api and indexer; redis from api and indexer; DNS egress; egress to Ollama host ipBlock |

**Query path (§3.2), fixed order in services/answer.py:** validate (3–500 chars, else 422) → follow-up check from browser history → cache check (skipped for follow-ups) → rewrite follow-ups into a standalone query → embed with the pinned model → retrieve top-k excluding superseded → relevance floor / abstain → augment (instructions, conversation context, numbered evidence, question) → generate (low temperature, schema-enforced) → validate (retry once, then canned) → citation check → store turn and cache if safe.

**Repository layout** follows brief §10 and AGENTS.md exactly; the checker looks for those paths. Additions: api/app/providers/cache/, api/app/config.py, indexer/pipeline/config.py, k8s/base/serviceaccounts and secret.placeholder.yaml, docs/decisions/, docs/handover/, docs/failure-log.md, docs/evidence/.

## Dev 1: RAG pipeline and evaluation

Dev 1 owns indexer/, api/app/{retrieval,providers,services}, api/app/config.py, eval/ and corpus/. Phases run in order; P1 starts on day one with no cluster.

### D1-P1 · Corpus selection (§2)

This is the first PR of the repo, so a weak corpus is corrected early.

1. **Pick documents.** Copy corpus/sources.example.yaml to sources.yaml and choose public FAST-NUCES documents covering all seven §2 properties: ≥6 docs and ≥40 pages; a genuine version pair (Academic Rules Aug 2023 vs Handbook Jun 2026); one scanned image-only PDF (confirm with pdffonts: empty font list); one document with an information-bearing table; one with long definitions (Student Handbook GenAI policy); exact-term content (clause numbers, course codes, CGPA thresholds, fees); one deliberately absent topic (default: hostel rules, Transport and Hostel Facilities PDF excluded).
   - Rules: public pages only, never SLATE/Flex/NU Mail, slides, LLM-generated or paywalled content. Never remove the pause in fetch.py.
2. **Fetch and manifest.** make fetch; python corpus/fetch.py --verify. Commit corpus/MANIFEST.md (URL + SHA-256) and sources.yaml. Never commit corpus/raw/. Confirm the 2023 rules PDF actually downloads; if not, record the substitute pair in DECISIONS.md.
3. **Write docs/CORPUS.md.** One row per property: which document, which page, which failure mode it makes reachable. Include the version pair's doc\_version values and which is superseded.
4. **Mark versions.** Make sure \_index.json gives each file the right doc\_version and superseded flag; document how the flag is set.

### D1-P2 · Golden set and eval harness (§5.1–§5.4)

Written before any tuning, from the documents, never from retriever output.

1. **Write eval/golden.yaml.** ≥15 questions: ≥8 ordinary, ≥2 version-sensitive, ≥2 exact-term, ≥2 must-abstain (on the absent topic), ≥1 prompt injection. Each lists its relevant passages by document and section (chunk ids change with chunk config, so prefer doc + section).
2. **Implement run\_eval.py functions.** recall\_at\_k (relevant retrieved in top k / total relevant; report k=3 and k=5, overall and by question type); citation\_validity (% of citations matching a retrieved passage); summarise; gate. Gate fails when recall@5 drops >5 points below baseline, any must-abstain question is answered from context, or citation validity < 95 %. Exit codes 0 pass, 1 gate failed, 2 not implemented.
3. **Check against fixtures.** make dev + make eval-fixtures against stubs to prove the harness end to end, then create the fixture baseline (eval/fixtures baseline file, separate from eval/baseline.json).
   - Rule: the two baselines are never mixed. Golden questions and baselines are never edited to make a gate pass; baseline updates are their own commit with a reason.

### D1-P3 · Indexing pipeline (§3.1, §4.4)

1. **extract.** PDF to text with page numbers; detect pages with no text layer and OCR them (OCR engine is a ponytail decision); strip repeating headers and footers but keep headings and section boundaries; handle the HTML tables (fee structure, grading) so columns stay aligned. Record OCR'd docs, a before/after mangled-table example and what could not be recovered for PIPELINE.md.
2. **clean.** Remove artefacts without destroying structure; document the rules and one thing deliberately not stripped.
3. **chunk.** Structure-aware with overlap: sections, then paragraphs, then sentences, under CHUNK\_SIZE with CHUNK\_OVERLAP from config; state the unit (tokens or characters). Never split a heading from its first paragraph. Every chunk carries source, section, page, doc\_version, superseded. Compute storage amplification (stored tokens / original tokens).
4. **embed.** One vector per chunk via Ollama with EMBED\_MODEL from config; never hard-code a model name or dimension.
5. **store.** The only Chroma writer. Write id, text, vector and metadata; leave a hook for the collection-metadata pin (model name and vector dimension), which Dev 2 builds as the swap task. Re-index must be safe to repeat (rebuild or upsert, ponytail decision).
6. **Invalidate the cache.** Last step of every run (Job and CronJob): expire the semantic cache in Redis (for example bump a version key). Requires Redis egress from the indexer.
7. **Tests.** Unit tests per stage on the fixture corpus; chunking keeps every metadata field and never orphans a heading; the --dummy mode still works and writes dummy-768 as its model.
8. **Corpus delivery to the Job.** How documents reach the Job (baked into the image, fetched at start-up, or a volume) is decided (Q4): the Job runs fetch.py at start-up into an emptyDir, verifies every file against MANIFEST.md SHA-256 and fails if any mismatch; CI overrides CORPUS\_DIR to the fixtures. Explained in PIPELINE.md.

### D1-P4 · Retrieval, abstention and generation (§3.2, §3.4, §3.5)

1. **ChromaRetriever.retrieve.** Read-only client to chroma:8000; embed the question with the pinned model; top-k from TOP\_K; metadata filter excludes superseded: true unless the question explicitly asks about an older version (rule for detecting that is a ponytail decision, logged in DECISIONS.md). Return scores as cosine similarity.
   - Rule: nothing under api/ calls add, upsert, delete, create\_collection or get\_or\_create\_collection.
2. **Relevance floor and abstention.** RELEVANCE\_FLOOR from the ConfigMap; if no chunk clears it, return answered\_from\_context: false with a "corpus does not cover this" message and skip generation.
3. **Provider interface and factory.** base interface; ollama.py (format= JSON schema, OLLAMA\_URL, LLM\_MODEL, TEMPERATURE 0–0.3 with a one-line justification in the ConfigMap); hosted.py (OpenAI-compatible JSON mode or response schema, HOSTED\_BASE\_URL, LLM\_API\_KEY from the Secret). Unknown LLM\_PROVIDER or RETRIEVER fails at startup, never defaults silently. A swap is one file plus one ConfigMap value.
4. **Augment.** Instructions first, then numbered and delimited evidence, then the question. Retrieved text and the question are data, never instructions.
5. **Validate, retry, fall back.** Parse with the Answer model; on failure retry exactly once, then return the canned safe response. Timeouts and provider outages also end in the canned response, never a 5xx. Retry and timeout logic lives once in services/, not in providers. reasoning is stripped before display.
6. **Citation check.** Drop any citation not matching a passage in this response's retrieved list (source, section, page). A claim-bearing answer left with no valid citation counts as a validation failure.
7. **Tests (never skipped).** validation failure → one retry → canned, no 500; invented citation dropped; nothing above the floor → abstain; superseded excluded by default; poisoned-chunk injection test; provider factory rejects unknown values. All with stubs only.

### D1-P4b · Conversation history and follow-ups (§3.2 steps 2 and 8, decided by the user)

The browser keeps the conversation; the API stays stateless. History drives follow-up detection and is sent to the model so it has context. This changes the starter-kit request and response contract, so it needs an ADR (docs/adr/0002 or next free number) before code.

1. **Store history in the browser.** Edit ui/index.html to save turns in localStorage (per tab or per conversation, with a "New conversation" reset). Each stored turn keeps the question and the displayed answer only, never reasoning or retrieved text. Wrap storage access in try/catch so the page works when storage is blocked.
2. **Window: recent turns verbatim, older turns summarised.** The browser sends the last N turns exactly (N = HISTORY\_TURNS in the ConfigMap, default 3) plus one running summary of everything older. When a turn falls out of the window, it is folded into the summary.
3. **Who writes the summary.** The API generates the updated summary with the configured provider (schema-constrained, low temperature) and returns it in the response; the browser stores it and sends it back next time. A failed summary call never fails the answer: the old summary is kept and the event is logged.
4. **Contract change.** The request gains optional history (list of {question, answer}, at most N) and summary (string, length-capped). The response gains the updated summary. Both are validated like the question (sizes capped, else 422). Requests without history behave exactly as today, so eval, CI and the 11 given tests keep working.
5. **Follow-up detection.** A question is a follow-up only when history is present and it depends on it (referential words, ellipsis, or too short to stand alone). The detection method (heuristic, LLM classifier, or both) is a ponytail decision recorded in DECISIONS.md with a measured false-positive check. With no history, it is never a follow-up.
6. **Retrieval for follow-ups.** Rewrite the follow-up into a standalone query using history before embedding, so "what about the fee?" retrieves fee passages. The rewrite is logged; retrieval, the superseded filter and the relevance floor apply to the rewritten query unchanged.
7. **Prompt order.** Instructions → conversation context (summary, then recent turns, delimited and labelled as prior conversation) → numbered evidence → the question. History is untrusted data like retrieved text: it can be edited in the browser, so it never overrides instructions and is never a citation source. Citations still must match this request's retrieved passages only.
8. **Cache and storage rules.** Follow-ups skip the cache check and are never cached. Standalone questions in a conversation are cached as normal, keyed on the question alone, never on history. Store the turn means log it (request\_id, follow-up flag, rewritten query), never persist history server-side.
9. **Tests (stubs only).** No history → never a follow-up and response unchanged; follow-up skips cache and is not stored in it; oversized history → 422; injected instruction inside history is not obeyed; summary failure still returns the answer; citations from history are dropped. Add at least two follow-up questions to the golden set as a separate type, scored but not part of the gate unless the user asks.
10. **Observability.** Add a follow-up counter and a summary-failure counter; history text is logged at DEBUG only.

### D1-P5 · Semantic cache on Redis (§3.3)

1. **Cache module** in api/app/providers/cache/: store question embedding + response; a hit is cosine similarity ≥ CACHE\_THRESHOLD from the ConfigMap. Redis address from config. Respect the invalidation version key the indexer bumps.
2. **Never cache:** follow-up questions (as detected in D1-P4b), abstentions, out-of-scope answers, canned fallbacks, anything that failed validation. Mark hits with "cached": true or X-Cache so the UI shows the chip.
3. **Redis down is not a 500.** Cache errors degrade to a miss; /readyz still reports Redis per §4.3.
4. **ADR** docs/adr/0003 (or next free number): Redis vs a second Chroma collection, with rejected alternatives.
5. **Tests:** abstentions and failed answers not cached; cache invalidated after an index run; threshold read from config.

### D1-P6 · Observability (§4.8)

1. **Logs.** JSON to stdout; request\_id on every line; one line per request with top\_k, retrieved chunk ids, scores and whether it abstained. Raw prompt at DEBUG only; no secrets, no stack traces in bodies.
2. **Metrics.** Add retrieval latency, generation latency, cache hit ratio, abstention count, fallback count, tokens in/out per request to the existing request count and latency. Bounded labels only.

### D1-P7 · Measure and tune on the real cluster (§3.1, §3.3, §5.2)

Needs Dev 2's cluster with RETRIEVER=chroma and LLM\_PROVIDER=ollama-host.

1. **Chunking.** At least three (CHUNK\_SIZE, CHUNK\_OVERLAP) configs; re-index each and record recall@5 in a PIPELINE.md table; ship the best and justify it.
2. **Relevance floor.** Choose with data so every must-abstain question abstains and ordinary recall holds; record the values tried.
3. **Cache threshold.** Lowest threshold with zero false hits on the test questions; report the 2–3 thresholds tried and the false hit that ruled one out.
4. **Baseline.** Run make eval; commit eval/results.json and eval/baseline.json (recall@3, recall@5 overall and by type, citation validity, abstention correctness = 100 %).
5. **Write the ConfigMap values** with comments pointing at the tables (handed to Dev 2 by PR).

### D1-P8 · Failure analysis and RAG write-ups (§5.5, §7)

1. **docs/FAILURE-ANALYSIS.md.** Break four of stages A–F one at a time (scanned PDF without OCR, 100-token no-overlap chunks, top\_k 1 or EMBED\_MODEL on API only, removed context instruction, removed superseded filter, temperature 1.2). For each: symptom, diagnosis, stage, remedy, and the metric or log line that would have shown it.
2. **docs/PIPELINE.md.** Per-stage report from P3 plus the measurement tables from P7; model name, dimension and where the pin lives.
3. **ENGINEERING-NOTES.md Q5 and Q6** with own file:line references (Q5: worst recall@5 by type and the RAG-lecture fix; Q6: what the pin guard does).

## Dev 2: Kubernetes, platform and CI/CD

Dev 2 owns the Dockerfiles, k8s/, .github/workflows/, Makefile additions and the platform docs. The whole system runs on minikube around the stubs before any RAG code lands.

### D2-P1 · Repository bootstrap and governance (§6, §8)

1. **Create the repo.** Unzip the starter kit, git init, initial commit and push under the user's own account (D8). Create dev.
2. **Protect main.** No direct pushes, PR required, CI required to pass (checks added once ci.yml exists), one approval. Screenshot to docs/evidence/.
3. **Docs skeleton.** docs/decisions/DECISIONS.md seeded with D1–D9; docs/AI-USAGE.md with a Task log section; docs/failure-log.md; docs/handover/; docs/evidence/; copy the brief to docs/planning/; commit CLAUDE.md and AGENTS.md.
4. **Verify the baseline.** make install, make test (11 tests), make lint, make dev all green before anything else.

### D2-P2 · Container images (§4.7, §6)

1. **api/Dockerfile** from pinned python:3.12.x-slim; non-root USER; no secrets in ENV/ARG; start command per STARTER.md; .dockerignore.
2. **indexer/Dockerfile** same base; entry python -m pipeline.run; must support --dummy; corpus delivery per the agreed decision.
3. **ui/Dockerfile** on pinned nginxinc/nginx-unprivileged; nginx.conf as /etc/nginx/nginx.conf; listens on 8080; writes only under /tmp.
4. **make images** builds all three and runs minikube image load; manifests use imagePullPolicy IfNotPresent.
   - Rules: every base image pinned; images run with a read-only root filesystem; no :latest anywhere.

### D2-P3 · Kubernetes base around the stubs (§4.1–§4.3, §4.6)

1. **make cluster.** minikube with --cni=calico, 6 GB, 4 CPUs, metrics-server and ingress addons.
2. **Base objects in k8s/base/.** Namespace rahbar; one ServiceAccount per workload; ConfigMap with every tunable (start with RETRIEVER=stub, LLM\_PROVIDER=stub, EMBED\_MODEL=dummy-768); secret.placeholder.yaml with REPLACE\_ME only and never listed in kustomization.yaml; make secret for the real one.
3. **chroma** StatefulSet, 1 replica, volumeClaimTemplates, chromadb/chroma:1.0.12, data /data; **redis** Deployment + PVC (redis:7.x with persistence); **api** Deployment 3 replicas with startup, liveness and readiness probes exactly as §4.3, maxSurge 1, maxUnavailable 0, terminationGracePeriodSeconds and a preStop sleep; **ui** Deployment with emptyDir /tmp.
4. **indexer** Job (restartPolicy OnFailure, backoffLimit set) and CronJob reindex (weekly, same image and args); re-index command kubectl create job --from=cronjob/reindex works.
5. **Services and Ingress.** Four ClusterIP Services (api, ui, chroma, redis); Ingress on rahbar.local, / → ui, /api → api.
6. **HPA** on api: minReplicas 3, maxReplicas 8, CPU utilisation.
7. **Overlays** k8s/overlays/dev and prod; kustomize build k8s/overlays/prod | kubeconform -strict passes and contains no :latest.
8. **Prove it.** Run the indexer with --dummy, ask through the Ingress, get the stub answer. Delete an api pod and show nothing breaks.
   - Rules: everything in namespace rahbar; no NodePort or LoadBalancer on Chroma or Redis; service-to-service addresses use Service DNS names, never localhost.

### D2-P4 · Security baseline (§4.7)

1. **Pod security on every workload.** runAsNonRoot, readOnlyRootFilesystem, capabilities drop ALL, automountServiceAccountToken false; writable paths as emptyDir.
2. **NetworkPolicy.** Deny all ingress and egress by default, then allow exactly: ui from the ingress controller; api from ui and ingress; chroma from api and indexer; redis from api and indexer; DNS egress to kube-dns on 53 UDP and TCP; api and indexer egress to the Ollama host ipBlock (IP from minikube ssh "grep host.minikube.internal /etc/hosts") or the hosted endpoint; indexer egress to nu.edu.pk on 443 for the start-up fetch (Q4).
3. **Prove it.** From the ui pod, a connection to chroma fails; from api it succeeds. Save the output to docs/evidence/.

### D2-P5 · Resources, scaling and rollouts (§4.5, §4.6)

Runs after Dev 1's real indexer and provider are switched on, because numbers must reflect real load.

1. **Measure.** Run a real index and a burst of questions; capture kubectl top pods; set requests and limits on every container (including Job and CronJob) from that output with a stated margin; commit the output to docs/evidence/.
2. **HPA reads a real value**, never unknown; capture kubectl get hpa.
3. **Scale and endpoints.** kubectl get endpoints showing ≥3 IPs without touching the Service.
4. **Rollout and undo.** Ship a visible change with kubectl set image, watch rollout status, then rollout undo and show the previous version serving. Capture evidence.
5. **Embedding-pin demonstration.** Change EMBED\_MODEL in the ConfigMap without re-indexing, restart the api, capture 0/1 READY and the log line naming both models.

### D2-P6 · CI pipeline, ci.yml (§6)

Triggers on pull requests to main and pushes to dev.

1. **lint** ruff and mypy. **test** pytest with coverage ≥60 % on the api app package, stub provider only. **manifests** kustomize build prod | kubeconform -strict. **build** api, ui and indexer images, no push on a PR. **scan** Trivy, fail on fixable HIGH or CRITICAL.
2. **e2e-eval** on kind: build and load images, apply manifests, run the indexer Job with CORPUS\_DIR=eval/fixtures, wait with kubectl rollout status / kubectl wait (never sleep), run eval/run\_eval.py with golden.fixture.yaml against the fixture baseline and enforce the gate. Models in CI: Ollama on the runner with nomic-embed-text only, LLM\_PROVIDER=stub (Q3). Built by Dev 1 as the swap task.
3. **Make all six jobs required checks** on main.
   - Rules: least-privilege permissions block on every workflow; no secrets printed; caching of dependencies is fine, caching of results that hide failures is not.

### D2-P7 · CD pipeline, cd.yml (§6)

1. **test → build-push → deploy** on push to main. build-push has needs: test, logs in with a Docker Hub access token from GitHub Secrets, pushes all three images tagged ${{ github.sha }}. deploy has needs: build-push, creates an ephemeral kind cluster, deploys by SHA, waits on rollout status and smoke-tests through the Ingress.
2. **Evidence.** Link to a successful cd.yml run and the Docker Hub tags for submission.

### D2-P8 · Gate demonstration (§6)

1. Open a PR that deliberately fails the eval gate (for example 100-token no-overlap chunks or a removed superseded filter on the fixture run), screenshot the greyed-out merge button, fix it, screenshot green. Close or revert the breaking change; never update a baseline to pass.

### D2-P9 · Platform docs (§4.2, §7, §10)

1. **docs/adr/0001-indexer-as-job.md** in own words (the first file the marker reads); **0004-llm-provider-and-data-governance.md** with Dev 1's input.
2. **ARCHITECTURE.md** including why Chroma is a StatefulSet.
3. **README.md** replacing the kit's: system summary, the exact apply order from a clean clone, make secret line, corpus note (MANIFEST + fetch script), and that embedding goes through the same Ollama host. Verify the order on a fresh make cluster.
4. **ENGINEERING-NOTES.md Q1–Q4** with own file:line references (indexing at startup, swapped probes under slow Chroma, what CPU HPA measures during generation, indexer peak memory and exit 137).

## The swap and the handoffs

Each dev does exactly one real task in the other's area, reviewed by the area's owner. The proposal below pairs each dev with the task closest to what they already know; the user confirmed it.

| Swap | Who | Task | Why this one |
| --- | --- | --- | --- |
| Dev 1 into platform | Dev 1 | Build the e2e-eval CI job (D2-P6 task 2) | It wraps run\_eval.py and the fixture baseline, which Dev 1 wrote |
| Dev 2 into RAG | Dev 2 | Build the embedding-pin guard: the indexer writes model + dimension into collection metadata, and /readyz refuses on mismatch, naming both values (§4.3, §4.4) | Dev 2 demonstrates it in D2-P5 and owns the probes that consume it |

When a dev works in the other's area, they read docs/handover/ first and follow the owner's layer rules (CLAUDE.md §3). The owner reviews the PR.

### Handoffs between the two lanes

| From | To | What is handed over | Needed for |
| --- | --- | --- | --- |
| Dev 1 (D1-P1) | Dev 2 | Corpus decided, MANIFEST committed | Indexer image and corpus delivery (D2-P2) |
| Dev 2 (D2-P3) | Dev 1 | Stub system running on minikube, make images working | Real pipeline tested in-cluster (D1-P4 onward) |
| Dev 1 (D1-P2) | Dev 2 | run\_eval.py implemented, fixture baseline committed | e2e-eval gate (D2-P6) |
| Dev 1 (D1-P3, D1-P4) | Dev 2 | Real indexer and provider merged to dev | ConfigMap switch to RETRIEVER=chroma, LLM\_PROVIDER=ollama-host; resource measurement (D2-P5) |
| Dev 2 (D2-P4) | Dev 1 | NetworkPolicy allowing indexer → redis and api/indexer → Ollama host | Cache invalidation and embeddings in-cluster |
| Dev 1 (D1-P7) | Dev 2 | Tuned ConfigMap values with measurement comments | Final manifests and baseline used by CI |
| Dev 2 (pin guard) | Dev 1 | /readyz pin check merged | D2-P5 demonstration and engineering note Q6 |

All handoffs travel as PRs into dev, never as direct pushes; the receiving dev reviews them.

## Definition of done and open questions

### A phase is done when

1. Every item on its caveman list is true and its starter-kit TODO markers are gone.
2. make test and make lint are green, coverage ≥ 60 %, make check shows no new violations, manifests pass kubeconform.
3. Any behaviour the brief asks to demonstrate has evidence in docs/evidence/.
4. Every tuned number has its measurement table in PIPELINE.md.
5. The CLAUDE.md §7 checklist was walked, skills and tasks are logged in AI-USAGE.md, and a handover file exists if the branch is not merging.

### The project is done when (shared close-out)

- [ ] grep -rn 'STARTER-[T]ODO' returns nothing; python scripts/check\_submission.py is clean
- [ ] A fresh make cluster + README apply order + indexer Job + make ask works from a clean clone
- [ ] eval/results.json and eval/baseline.json committed; abstention correctness 100 %, citation validity ≥ 95 %
- [ ] Successful cd.yml run link and Docker Hub SHA tags recorded
- [ ] All required docs written, ENGINEERING-NOTES Q7 written from failure-log.md
- [ ] No secret anywhere in git history; no Claude attribution in any commit or PR

### Open questions for the user

The user answered all of these; each answer becomes a DECISIONS.md row in the bootstrap phase. Q6 is deferred until the project is complete.

| # | Question | Options | Recommended |
| --- | --- | --- | --- |
| Q1 | Which swap tasks? | (a) Dev 1 builds e2e-eval, Dev 2 builds the embedding-pin guard; (b) Dev 1 writes one manifest set (e.g. NetworkPolicy), Dev 2 builds the Redis cache | Decided: (a) |
| Q2 | Resolved: how are follow-up questions detected? | Browser-stored history: last N turns verbatim plus a summary of older turns, sent with each request, used for follow-up detection and included in the prompt (D1-P4b, D10) | Decided by the user |
| Q3 | How does e2e-eval in CI get embeddings and an LLM? | (a) Ollama on the runner with nomic-embed-text only, LLM\_PROVIDER=stub; (b) Ollama with both models (slower CI); (c) hosted LLM with a key in GitHub Secrets | Decided: (a) |
| Q4 | How do documents reach the indexer Job? | (a) Fetched at Job start into an emptyDir with fetch.py --verify; (b) baked into the indexer image; (c) a pre-filled PVC | Decided: (a) |
| Q5 | Which topic is deliberately absent? | Hostel rules (exclude the Transport and Hostel Facilities PDF), or another of your choice | Decided: hostel rules |
| Q6 | Any bonus scope? | ollama-incluster; hybrid BM25 + vector retrieval for exact terms; neither | Deferred: decided after the project is complete; neither is built until then |
