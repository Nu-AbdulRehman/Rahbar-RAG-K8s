# AGENTS.md — RAHBAR

Operational reference for any coding agent working in this repo (Claude Code, Codex,
Cursor, etc.). For the non-negotiable rules, read `CLAUDE.md` first. This file assumes
you have, doesn't restate the "never" list, and tells you how to move.

## Project

Two-developer build of RAHBAR, a grounded RAG question-answering service over FAST-NUCES
public documents, deployed on Kubernetes (Assignment 02, due **Sun 8 Nov 2026, 23:59
PKT**). API: FastAPI + Pydantic v2 on Python 3.12. Vector store: ChromaDB
(`chromadb/chroma:1.0.12`, client `chromadb-client==1.0.12`). Semantic cache: Redis.
UI: the starter kit's static chat page on `nginxinc/nginx-unprivileged`. LLM: Ollama on
the host (`LLM_PROVIDER=ollama-host`, `llama3.2:3b`) by default, with `hosted` kept as a
one-file swap and `stub` for every test and CI run. Embeddings: `nomic-embed-text` through
the same Ollama host. Local cluster: minikube with Calico, `metrics-server` and `ingress`.
CI clusters: kind. CI/CD: GitHub Actions, images on Docker Hub tagged by commit SHA.

**Status:** the repo starts as the starter kit (`STARTER.md`). Every function we own raises
`NotImplementedError` next to a starter-kit `TODO(section)` marker. Find the open work with
`grep -rn 'STARTER-[T]ODO' --exclude-dir=.venv .`. The kit has no Dockerfiles, manifests, or
workflows. All of those are ours.

**Order of work** (STARTER.md "How the week runs"): first, the whole system on minikube
around the stubs (`RETRIEVER=stub`, `LLM_PROVIDER=stub`, indexer `--dummy`,
`EMBED_MODEL=dummy-768`). Then replace the stubs with the real pipeline, provider, cache,
abstention, eval, and the CI gate. Never wait on the RAG pieces to start the Kubernetes
work.

## Repo layout

```
api/                        FastAPI service: reads the index, never writes it
  app/schemas.py            Answer, Citation, AskResponse: the contract
  app/config.py             the api's ONLY environment reader
  app/routes/               /api/ask, /healthz, /readyz, /metrics
  app/services/answer.py    the 8 query steps, in order
  app/retrieval/            stub.py (given), chroma.py (ours)
  app/providers/llm/        base, stub (given), ollama, hosted (ours)
  app/providers/cache/      semantic cache + invalidation (ours)
  tests/                    keep the 11 given tests passing; add ours
  Dockerfile · .dockerignore
indexer/                    the Job's image: the only writer
  pipeline/run.py           python -m pipeline.run [--dummy]
  pipeline/{extract,clean,chunk,embed,store}.py
  pipeline/config.py        the indexer's ONLY environment reader
  tests/ · Dockerfile · .dockerignore
ui/                         index.html + nginx.conf (given); Dockerfile (ours)
corpus/                     fetch.py, sources.yaml, MANIFEST.md; raw/ is gitignored
eval/                       golden.yaml, run_eval.py, baseline.json, results.json
  fixtures/                 3 fixture docs + golden.fixture.yaml, used by CI
k8s/base/                   namespace, api, ui, chroma-statefulset, redis, indexer-job,
                            reindex-cronjob, services, ingress, configmap,
                            networkpolicy, hpa, serviceaccounts, kustomization.yaml,
                            secret.placeholder.yaml (NOT in kustomization.yaml)
k8s/overlays/{dev,prod}/
docs/                       CORPUS.md, PIPELINE.md, FAILURE-ANALYSIS.md, ARCHITECTURE.md,
                            ENGINEERING-NOTES.md, AI-USAGE.md, failure-log.md,
                            decisions/DECISIONS.md, adr/, evidence/, handover/,
                            planning/RAHBAR_Problem_Statement.pdf
scripts/check_submission.py
.github/workflows/{ci.yml,cd.yml}
Makefile · README.md · .gitignore · LICENSE
```

Required ADRs: `0001-indexer-as-job.md` (the first file the marker reads, in our own
words), one on the semantic cache store (Redis vs a second Chroma collection), and
`0004-llm-provider-and-data-governance.md`. The reason Chroma is a StatefulSet goes in
`ARCHITECTURE.md`. Any starter-kit contract change needs its own ADR.

## Commands

Only commands the brief or STARTER.md names. `make` with no target lists them all. Add new
ones here in the same PR that creates them.

```bash
make install                 # .venv + api, indexer and dev deps
make test                    # stub-only pytest: no cluster, no model, no network
make lint                    # ruff + mypy
make dev                     # api with stubs on http://localhost:8000, serves the UI
make cluster                 # minikube start --driver=docker --cni=calico --memory=6144 --cpus=4
                             #   + addons metrics-server and ingress
make images                  # build api, ui, indexer and `minikube image load` them
make secret                  # kubectl create secret generic rahbar-secret -n rahbar from $LLM_API_KEY
make fetch                   # corpus download to corpus/raw/, writes MANIFEST.md
python corpus/fetch.py --verify          # re-hash local files against MANIFEST.md
make eval                    # run_eval.py through the Ingress
make eval-fixtures           # run_eval.py against `make dev` with the fixture golden set
make ask INGRESS_IP=127.0.0.1            # with `minikube tunnel` on macOS/Windows
make check                   # scripts/check_submission.py; run before every PR

OLLAMA_HOST=0.0.0.0 ollama serve         # must listen on all interfaces
ollama pull llama3.2:3b && ollama pull nomic-embed-text

kustomize build k8s/overlays/prod | kubeconform -strict
kustomize build k8s/overlays/prod | grep -c ':latest'     # must print 0
kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar   # re-index, no redeploy
python eval/run_eval.py --api http://<ip> --host rahbar.local --update-baseline  # deliberate improvements only
```

`run_eval.py` exit codes are the gate: 0 pass, 1 gate failed, 2 not implemented yet.

When a cluster breaks: `kubectl get pods` → `kubectl describe pod` (Events) →
`kubectl logs [--previous]`. The brief's §9 traps table covers the usual causes:
ImagePullBackOff (use `minikube image load` + `IfNotPresent`), DNS dead after a
NetworkPolicy (allow kube-dns 53 UDP+TCP), api can't reach Ollama (`OLLAMA_HOST=0.0.0.0` +
egress `ipBlock` for `host.minikube.internal`), ui reaches chroma (cluster wasn't started
with Calico), HPA `<unknown>` (no `requests.cpu` or no metrics-server), indexer exit 137
(raise its memory limit, guided by `kubectl top pods`).

## CI shape (brief §6)

- `ci.yml` runs on PRs to `main` and pushes to `dev`. Jobs: `lint` (ruff, mypy), `test`
  (pytest, coverage ≥ 60 % on the api app package, stubs only), `manifests` (kustomize |
  kubeconform -strict), `build` (api, ui, indexer, no push), `scan` (Trivy, fails on
  fixable HIGH/CRITICAL), `e2e-eval` (kind cluster, apply manifests, run the indexer Job
  with `CORPUS_DIR=eval/fixtures`, wait for rollout, run `eval/run_eval.py`, enforce the
  gate). All are required checks on `main`.
- `cd.yml` runs on pushes to `main`: `test` → `build-push` (`needs: test`, Docker Hub,
  tagged `${{ github.sha }}`) → `deploy` (`needs: build-push`, ephemeral cluster,
  `kubectl rollout status`, smoke test through the Ingress).
- Waits poll readiness (`kubectl rollout status`, `kubectl wait`), never `sleep`.
- Evidence to capture: a PR that fails the eval gate with the greyed-out merge button,
  then the fixed green run.

## Environment

All configuration is environment variables, from the ConfigMap and Secret on the cluster
(STARTER.md "Configuration"). One image runs everywhere.

Given keys: `RETRIEVER` (`stub|chroma`), `LLM_PROVIDER`
(`stub|ollama-host|ollama-incluster|hosted`), `EMBED_MODEL` (the pin, one ConfigMap key
read by both programs), `CHROMA_HOST`/`CHROMA_PORT` (`chroma`/`8000`),
`CHROMA_COLLECTION` (`rahbar`), `TOP_K` (5), `TEMPERATURE` (0.2), `LLM_MODEL`,
`OLLAMA_URL` (`http://host.minikube.internal:11434`), `HOSTED_BASE_URL`, `LLM_API_KEY`
(Secret only), `LOG_LEVEL`, `CORPUS_DIR` (`/corpus`), `CHUNK_SIZE`/`CHUNK_OVERLAP`
(400/50, unit stated in `PIPELINE.md`).

Keys we add, in `api/app/config.py` and `indexer/pipeline/config.py` the same way:
relevance floor, cache similarity threshold, Redis host/port. Every new key gets a line in
the ConfigMap with a comment saying where its value came from (a measurement table, or a
one-line justification for `TEMPERATURE`).

Never require a key on the default path: `make install && make test && make dev` must work
with nothing else. Service DNS names: `api`, `ui`, `chroma`, `redis`. Namespace: `rahbar`.
Ingress: `/` → ui, `/api` → api, on one host (`rahbar.local`). Ports: api 8000, ui 8080,
chroma 8000 (heartbeat `GET /api/v2/heartbeat`, data in `/data`), redis 6379.

## Conventions

- **Git:** feature branch → `dev` → `main`. Branch name `<type>/s<section>-<desc>`, for
  example `feat/s4.4-embed-pin`, with type one of
  `feat|fix|docs|test|ci|refactor|chore`. Conventional Commits that cite the brief
  section. One PR per branch with a substantive partner review. The first PR names the
  corpus, so a weak choice gets corrected early.
- **Identity:** commit and push only as the user's own configured account (the existing
  `git config user.name`/`user.email` and their own `gh auth`). Claude never appears as a
  contributor. Never change the author or committer, never push with a Claude, bot, or
  App identity, and never add `Co-Authored-By: Claude`, `Claude-Session:`, or "Generated
  with Claude Code" lines to commits, PRs, or comments. If the identity is missing or
  looks like a bot, stop and ask. AI use is disclosed only in `docs/AI-USAGE.md`. Full
  rule: `CLAUDE.md` §1.23.
- **Accounts:** Dev 1's work (pipeline, eval, the `e2e-eval` job) goes through
  Nu-AbdulRehman. Dev 2's work (Dockerfiles, `k8s/`, workflows, the embedding-pin guard)
  goes through MTH99910: commits, PRs and reviews. Each account reviews the other dev's
  PRs. If the configured account doesn't match the owner of the work, stop and ask.
- **Ownership:** Dev 1 owns the RAG pipeline and eval, Dev 2 owns the platform
  (Dockerfiles, `k8s/`, workflows). Each partner does one real task in the other's area.
- **Handover:** a session that ends with an unmerged branch leaves
  `docs/handover/HANDOVER-<branch>.md`. It records position, what's green, what's
  half-done, the literal next command, and what will bite. Write it at close and read it
  at open. Delete it in the merge commit.
- **Decisions:** a decision the brief doesn't dictate becomes a row in
  `docs/decisions/DECISIONS.md`. Significant ones get an ADR, and anything to defend at
  the viva gets a paragraph in `ENGINEERING-NOTES.md`. Never re-decide a resolved row.
- **Logs:** structured JSON to stdout, never a file. Every line has `request_id` (from
  `X-Request-ID` or generated). One line per request with `top_k`, the retrieved chunk
  ids, their scores, and whether it abstained.
- **Metrics** on `/metrics`: request count and latency, retrieval latency, generation
  latency, cache hit ratio, abstention count, fallback count, tokens in/out per request.
  Labels are bounded.
- **Engineering notes:** the seven questions in brief §7 are answered with our own
  `file:line` references. A generic answer scores zero.
- **Failures:** append to `docs/failure-log.md` when something breaks, not afterwards.
  `FAILURE-ANALYSIS.md` breaks four of the six stages (A–F) on purpose, one at a time.

## Skill cadence

Two Claude Code skills are mandatory at fixed points in every session, and one is
recommended:
- `caveman` (**mandatory**): at phase start, produces a stripped task list tagged with
  brief sections (`§N.N`).
- `ponytail` (**mandatory**): at every design fork, produces a decision stub with its
  rejected alternatives.
- `grilling` (**recommended**): whenever you need requirements or details from the user
  that the brief, STARTER.md, and `DECISIONS.md` don't already answer. Ask instead of
  guessing, and record the answers in `DECISIONS.md`.

Separately, a **pre-PR hardening review** is mandatory before every PR (no skill): at least
3 findings with `file:line` on the diff against `dev`, each fixed or marked `WONTFIX`.

Full trigger conditions and acceptance tests are in `CLAUDE.md` §6. That is the
authority. This is the reminder that the cadence applies to every session, not only the
first. Log every skill invocation in `docs/AI-USAGE.md` when it happens, including what
you overrode and why.

## Task log

After you complete any task, append a 1–2 line entry to the `## Task log` section of
`docs/AI-USAGE.md` before reporting completion:
`- <date> · <branch> · <what was done>`. This is separate from the skill-invocation
entries above. Full rule: `CLAUDE.md` §8.

## Definition of done for a phase

"The code runs" is not enough. A phase is done when:
1. Every item on the phase's `caveman` task list is demonstrably true, and its
   starter-kit TODO markers are gone.
2. `make test` and `make lint` are green and coverage holds at ≥ 60 %.
3. `make check` reports no new violations, and the manifests pass kubeconform.
4. The behaviour the brief asks you to *demonstrate* has its evidence committed in
   `docs/evidence/`: `kubectl top pods`, `kubectl get endpoints` with ≥3 IPs, the HPA
   reading a real value, rollout + `rollout undo`, the embedding-pin pod at 0/1 READY
   with its log line, branch protection, and the blocked merge.
5. Any tuned number has its measurement table in `PIPELINE.md` (chunking, cache
   threshold, relevance floor).
6. A handover file exists if the branch isn't merging immediately.
7. `caveman` and `ponytail` (if a fork occurred) fired at their required points, the
   pre-PR hardening review ran, `grilling` was used wherever user input was needed, and
   all of it is logged in `docs/AI-USAGE.md`, per `CLAUDE.md` §6.
8. Every completed task has its entry in the `docs/AI-USAGE.md` task log, per
   `CLAUDE.md` §8.

## Where to look when stuck

| Question | File |
|---|---|
| What does the API actually promise? | `STARTER.md` "The contract", `api/app/schemas.py` |
| What must never break? | `CLAUDE.md` §1–§2, brief §8 |
| Was this already decided? | `docs/decisions/DECISIONS.md`, `docs/adr/` |
| Which section does this TODO belong to? | the starter-kit `TODO(section)` comment, then the brief |
| Which env var, port, or image version? | `STARTER.md` "Configuration" and "Images and ports" |
| Why is my pod not ready / crashing? | brief §9 traps table, `docs/failure-log.md` |
| What does the corpus need to contain? | brief §2, `docs/CORPUS.md` |
| How is eval scored and gated? | brief §5, `eval/run_eval.py` |
| Is this a trap someone already hit? | `docs/failure-log.md`, any `docs/handover/*` |
