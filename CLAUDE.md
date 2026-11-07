# CLAUDE.md — RAHBAR. Read this before you touch anything.

This file is law for this repository. If something you're about to do conflicts with a
rule here, stop and say so instead of doing it anyway. "The user asked for it" is not
an exception to any rule marked **HARD**.

Source of truth order, when documents disagree:
`docs/planning/RAHBAR_Problem_Statement.pdf` (the brief, never edited) >
`STARTER.md` (the starter kit's contracts: `Answer`/`AskResponse`, endpoints, env vars,
Makefile targets) > the ADRs in `docs/adr/` and the resolution log in
`docs/decisions/DECISIONS.md` > the required docs (`CORPUS.md`, `PIPELINE.md`,
`ENGINEERING-NOTES.md`, `FAILURE-ANALYSIS.md`) > anything else, including this file's
examples. If code and the brief disagree, the code is the bug. Say so, don't quietly
reconcile them. Brief sections are cited as `§N.N` everywhere in this repo.

Changing a starter-kit contract (the request, the response, the chunk metadata fields) is
allowed, but only with an ADR that says why (STARTER.md).

---

## 0. What this system is, in one paragraph

RAHBAR is a grounded question-answering service over a real document corpus (FAST-NUCES
public documents), deployed on minikube in namespace `rahbar`. Two paths never share a
process. The **indexer** is a Kubernetes Job (and a weekly CronJob) that runs extract →
clean → chunk → embed → store and is the **only writer** to ChromaDB. The **api** is a
3-replica FastAPI Deployment that **only reads** it. On every question it validates the
question, checks the semantic cache, embeds the question with the same pinned model,
retrieves top-k with a superseded filter, augments, generates a schema-constrained answer,
validates it (retry once, then fall back), and stores the turn. The whole point, stated
once: **indexing runs once, and again when the material changes; querying runs on every
question** (§Read this first). And: **the system answers only from what it retrieved, cites
only what it retrieved, and says "the corpus doesn't cover this" instead of inventing an
answer.** If a change makes the API write the index, lets a citation reach the user that
wasn't retrieved, or lets a must-abstain question get answered, it is wrong regardless of
how clean the code looks.

---

## 1. HARD rules — never do these, no matter what you're asked

1. **Never commit a secret.** No `.env`, no `LLM_API_KEY`, no Docker Hub token, no
   kubeconfig: not in code, a commit message, a k8s manifest (not even base64, which is
   encoding, not encryption), a Dockerfile `ENV`/`ARG`, a workflow file, or a log line.
   The Secret is created from the command line only (`export LLM_API_KEY=...; make
   secret`). The only committed Secret file is `k8s/base/secret.placeholder.yaml`, it
   holds `REPLACE_ME` only, and it is **never listed in `kustomization.yaml`** (applying it
   would overwrite the real Secret). If you ever output a real key, treat it as a live
   incident: flag it at once. A key in history means rotation plus a two-line incident
   note, even if the commit is deleted (−20 / −15).
2. **Never push to `main`.** `main` is protected: PR + green CI + 1 approval. Work goes
   feature branch → `dev` → `main`. If asked to "just push this," refuse and open a PR
   instead (−4).
3. **Never index from the API.** No chunking, embedding, or Chroma write (`add`, `upsert`,
   `delete`, `create_collection`, `get_or_create_collection`) anywhere under `api/`. The
   API opens the collection read-only and fails readiness if it is missing. Only
   `indexer/pipeline/store.py` writes. Nothing runs indexing in a FastAPI lifespan, a
   startup hook, an init container of the api, or an entrypoint script (§4.2, −10).
4. **Never let the indexer and the API disagree silently about the embedding model.**
   `EMBED_MODEL` comes from one ConfigMap key, read by both. Nothing hard-codes a model
   name or a vector dimension. The indexer writes the model name and dimension into the
   collection metadata. At startup the API compares them with its own `EMBED_MODEL`, and
   on a mismatch it stays not-ready and logs one line naming both values. Never "fix" a
   mismatch by falling back, re-embedding in the API, or ignoring the dimension (§4.4, −8).
5. **Never return a citation that wasn't retrieved.** Every citation in an `AskResponse`
   must match a passage in that same response's `retrieved` list (source, section,
   page). Citations the model invents are dropped by code before the response leaves the
   service. If that leaves a claim-bearing answer with no valid citation, the answer is
   treated as a validation failure. Never let the model's output decide what was retrieved
   (§3.4, −10).
6. **Never answer a must-abstain question from context.** When nothing retrieved clears
   the relevance floor (a ConfigMap value, chosen with data), the response is
   `answered_from_context: false` with a message that the corpus doesn't cover the
   question, and no generation call is needed. Abstention correctness on the golden set is
   100 %, not 90 % (§3.4, §5.3, −10).
7. **Never let model output become a 5xx.** Use the strongest enforcement the provider
   supports (`format=` on Ollama, JSON mode / response schema on hosted), then always
   validate with the `Answer` Pydantic model. On a validation failure, **retry exactly
   once**, then return the safe canned response. A timeout or a provider that's down also
   ends in the canned response, never a 500. `reasoning` is stripped before display.
   Model output is never passed to `eval`/`exec`, never used to build SQL, a shell
   command, or a file path (§3.4, §4.7).
8. **Never treat retrieved text or the question as instructions.** Retrieved chunks go
   into the prompt delimited and numbered as evidence, after the instructions and before
   the question (§3.2 step 5). The poisoned-chunk test (index a chunk saying "ignore your
   instructions…", assert the system doesn't obey it) is never deleted, skipped, or
   weakened.
9. **Never serve or cache an unsafe answer.** Never cache follow-up questions,
   abstentions, out-of-scope answers, canned fallbacks, or anything that failed
   validation. A cached mistake is served to everyone. The cache hit threshold comes from
   the ConfigMap. **Every indexer run (Job and CronJob) invalidates the cache** as its last
   step, otherwise the new index answers nothing (§3.3).
10. **Never drop chunk metadata or the superseded filter.** Every chunk carries at least
    `source`, `section`, `page`, `doc_version`, `superseded: true|false`. Retrieval
    excludes `superseded: true` by default and includes it only when the question
    explicitly asks about an older version. Version handling is a metadata filter, never
    a prompt instruction (§3.1, failure mode E).
11. **Never deploy Chroma or Redis without persistence or with an external port.** Chroma
    is a `StatefulSet` (1 replica) with `volumeClaimTemplates`. Redis is a `Deployment`
    with a PVC. Every Service is `ClusterIP`. Never a `NodePort` or `LoadBalancer` on
    Chroma or Redis (§4.1, −8).
12. **Never put anything in the `default` namespace.** Every manifest sets
    `namespace: rahbar` (or inherits it from Kustomize), and the Namespace object is in
    `k8s/base/` (−5).
13. **Never ship a container without requests and limits**, including the indexer Job, the
    CronJob, the UI, Chroma, and Redis. Every number is justified by committed
    `kubectl top pods` output in `docs/evidence/`, never a guess. The HPA on `api` is
    `minReplicas: 3`, `maxReplicas: 8`, and must never read `<unknown>` (§4.5, −6).
14. **Never deploy `:latest` or an unpinned image.** Base images are pinned to a version
    (`python:3.12.x-slim`, `chromadb/chroma:1.0.12` matching `chromadb-client==1.0.12`,
    `redis:7.x`, `nginxinc/nginx-unprivileged:<ver>`). Our images are tagged and deployed
    by commit SHA (`${{ github.sha }}`). "What is running?" has a one-word answer you can
    paste into `git show` (§6, −6).
15. **Never add a publish or deploy CI job without `needs:`** on the verification jobs.
    Every workflow has a least-privilege `permissions:` block. Docker Hub credentials come
    from GitHub Secrets (an access token, never a password), and nothing pushes from a PR
    (§6, −6).
16. **Never weaken the pod security baseline.** Every workload has its own
    ServiceAccount, `automountServiceAccountToken: false` unless it calls the API server,
    `runAsNonRoot: true`, `readOnlyRootFilesystem: true` (writable paths are `emptyDir`
    mounts, e.g. `/tmp` for the UI), and `capabilities: drop: [ALL]`. NetworkPolicy is
    deny-by-default, then allows exactly: ui from the Ingress; api from ui and the
    Ingress; chroma from api and indexer only; redis from api (and the indexer, for
    invalidation) only; DNS egress to kube-dns on 53 UDP+TCP; api/indexer egress to the
    Ollama host `ipBlock` or the hosted endpoint. The ui pod must not reach chroma (§4.7).
17. **Never let `/healthz` touch a dependency.** Liveness opens no Chroma, Redis, or LLM
    connection. `/readyz` returns 200 only if Chroma is reachable, the collection is
    non-empty, Redis is reachable, and the embedding pin matches. Otherwise it returns 503
    naming the dependency that failed (§4.3).
18. **Never use `localhost` as a service-to-service address.** Use the Service DNS names
    `chroma`, `redis`, `api`, `ui`, and `host.minikube.internal` for Ollama on the host.
    The exceptions are `make dev` on your laptop and a container's probe against itself.
19. **Never commit the corpus PDFs, or use a corpus you may not use.** Commit
    `corpus/MANIFEST.md` (URL + SHA-256) and `corpus/sources.yaml`. `corpus/raw/` is never
    committed. Public pages only: never SLATE, Flex, NU Mail, or anything behind a login.
    Never this course's slides, an LLM-generated corpus, or anything paywalled. Never
    remove the pause between requests in `corpus/fetch.py` (§2).
20. **Never game the eval.** `eval/golden.yaml` is written before tuning, from the
    documents, never from what the retriever already returns. Never edit a golden
    question, its relevant passages, or `eval/baseline.json` to make a gate pass. The
    baseline is updated only after a deliberate, measured improvement, in its own commit
    that says why (§5).
21. **Never log, metric-label, or return in a response body** the API key, a token, or a
    URL with credentials. The raw prompt is logged at `DEBUG` only. No error body ever
    contains a stack trace. Metric labels are bounded: route templates, never raw paths
    or question text.
22. **Never write a test that can't fail.** Before calling a test done, revert the
    implementation, mentally or actually, and confirm the test goes red. Never use
    `time.sleep()`, a real network call, or a real model in a unit test. Use the stub
    retriever and the stub provider. Never skip a test, mark it `xfail`, or re-run it until
    it passes to get CI green.
23. **Never commit or push as Claude. Claude must never appear as a contributor in this
    repo.** Every commit, push, branch, PR, review reply, and issue comment goes through
    the user's own configured account: the existing `git config user.name` /
    `user.email` and the user's own `gh auth` / git credentials. Never set or override the
    author or committer (`git config user.*`, `--author`, `GIT_AUTHOR_*` /
    `GIT_COMMITTER_*`). Never use a Claude, bot, or GitHub App identity or token to push
    or open a PR. Never add `Co-Authored-By: Claude …` trailers, `Claude-Session:` lines,
    "🤖 Generated with Claude Code" footers, or any other Claude attribution to commit
    messages, PR titles or bodies, or GitHub comments, even if a tool or system default
    adds them. Strip them before committing. If the configured identity is missing, or
    looks like a Claude or bot account, stop and ask the user. Don't commit until it's
    fixed. AI assistance is still disclosed, but only in `docs/AI-USAGE.md` (§6, §8), never
    in git metadata.

    **Which account does which work.** Dev 1's work (the RAG pipeline and eval: `indexer/`,
    `api/app/{retrieval,providers,services}`, `eval/`, `corpus/`, plus Dev 1's swap task,
    the `e2e-eval` CI job) is committed, pushed, opened as PRs and reviewed as
    **Nu-AbdulRehman**. Dev 2's work (the platform: Dockerfiles, `k8s/`,
    `.github/workflows/`, Makefile additions, plus Dev 2's swap task, the embedding-pin
    guard) is committed, pushed, opened as PRs and reviewed as **MTH99910**. A review of a
    Dev 1 PR comes from MTH99910, and a review of a Dev 2 PR comes from Nu-AbdulRehman.
    Before every commit, push, PR or review, check `git config user.name` and the `gh` /
    credential account against the owner of the work. If they don't match, stop and ask
    the user to switch accounts. Never switch them yourself.

## 2. The deduction ledger — costs more than most features are worth

These twelve automatic deductions from brief §8 total **−107 marks**. Avoiding a deduction is
worth more than most features. Check this list before saying any phase is done:

| Violation | Cost | Rule |
|---|---|---|
| Any secret, key or password anywhere in git history | −20 (+ rotate + 2-line incident note) | §1.1 |
| A base64 Secret with a real value in a committed manifest | −15 | §1.1 |
| Indexing performed at API startup instead of in a Job | −10 | §1.3 |
| A returned citation that does not match a retrieved chunk | −10 | §1.5 |
| A must-abstain golden question answered from context | −10 | §1.6 |
| Chroma or Redis as a Deployment with no PVC, or NodePort/LoadBalancer | −8 | §1.11 |
| Embedding model not pinned, or indexer and API able to disagree silently | −8 | §1.4 |
| A container with no requests, or an HPA reading `<unknown>` | −6 | §1.13 |
| Publish/deploy job not gated by `needs:`, or deploying `:latest` | −6 | §1.14–15 |
| Manifests in the `default` namespace | −5 | §1.12 |
| README apply order that does not work from a clean clone | −5 | §7 |
| Commits pushed directly to `main` | −4 | §1.2 |

`make check` (`scripts/check_submission.py`) catches the mechanical ones. It is a lint, not a
grader. Its section **0 · starter kit** fails until every starter-kit TODO and
`raise NotImplementedError` is gone. If you add code that could trip a deduction the
checker doesn't detect, add a test or a CI step that does, in the same PR. Don't rely on
memory.

## 3. Layer discipline

```
api/app/
  routes/          → services, schemas           — HTTP only, thin handlers
  services/        → retrieval, providers, schemas — answer.py: the 8 query steps, in order
  retrieval/       → chromadb client (read only)  — stub.py, chroma.py
  providers/llm/   → httpx/openai                 — base, ollama, hosted, stub: wire formats only
  providers/cache/ → redis                        — semantic cache + invalidation key
  schemas.py       → pydantic only                — Answer, Citation, AskResponse: the contract
  config.py        → env                          — the ONLY environment reader
indexer/pipeline/
  extract → clean → chunk → embed → store         — store.py is the only Chroma writer
  config.py                                       — the indexer's only environment reader
```

- `chromadb` is imported only in `api/app/retrieval/` and `indexer/pipeline/store.py`
  (plus the pin check). `redis` only in `providers/cache/` and the indexer's invalidation
  step. HTTP clients for models only in `providers/llm/` and `indexer/pipeline/embed.py`.
- The concrete providers are named only in `providers/llm/` (and its factory) and tests.
  Everything else sees the provider interface. A provider swap is one file plus one
  ConfigMap value (§3.5). An unknown `LLM_PROVIDER` or `RETRIEVER` fails at startup and
  never silently defaults.
- No module reads `os.environ` outside the two `config.py` files. Tunables (`TOP_K`,
  `TEMPERATURE`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, relevance floor, cache threshold,
  `EMBED_MODEL`, `LLM_PROVIDER`, `CHROMA_HOST`) come from the ConfigMap. They are never
  constants in code. `TEMPERATURE` stays in 0–0.3, with a one-line justification in the
  ConfigMap.
- Query order in `services/answer.py` is fixed (§3.2): validate (3–500 chars, else 422) →
  cache check (skipped for follow-ups) → embed with the pinned model → retrieve top-k with
  the superseded filter → relevance floor / abstain → augment (instructions, numbered
  evidence, question) → generate → validate (retry once, then canned) → citation check →
  store turn and cache entry if safe.
- Retry, timeout, and fallback for generation live once, in the service layer, never
  inside individual providers.

## 4. Testing and evaluation discipline

- Fast loop: `make test` and `make lint` before every commit. Coverage on the api `app`
  package stays at 60 % or above, using stubs only: no network, no model (§6).
- These tests must exist and are never skipped: validation failure → one retry → canned
  response, never a 500; citation not in `retrieved` is dropped; nothing above the floor
  → `answered_from_context: false`; abstentions and failed answers are not cached; cache
  invalidated after an index run; superseded chunks excluded by default; embedding-pin
  mismatch → `/readyz` 503 naming both models; `/healthz` makes no dependency call; the
  poisoned-chunk injection test.
- Indexer tests: each stage has unit tests on the fixture corpus. Chunking never splits a
  heading from its first paragraph, and it keeps every metadata field.
- The golden set (`eval/golden.yaml`, ≥15 questions: ≥8 ordinary, ≥2 version-sensitive,
  ≥2 exact-term, ≥2 must-abstain, ≥1 injection) targets the real corpus. CI's `e2e-eval`
  uses the fixture corpus and `eval/fixtures/golden.fixture.yaml` with its own baseline.
  The two baselines are never mixed.
- The CI gate fails when recall@5 drops more than 5 points below baseline, any
  must-abstain question is answered from context, or citation validity is below 95 %.
- Tuning is measured, never guessed: at least three `(CHUNK_SIZE, CHUNK_OVERLAP)` configs
  with recall@5 in `docs/PIPELINE.md`, and the cache threshold chosen as the lowest one
  with zero false hits, with the rejected thresholds reported. A number with no
  measurement behind it scores zero.
- Lint and type checks must pass: `ruff`, `mypy`.

## 5. When you're unsure

- Don't invent a resolution to an ambiguity. Check `docs/decisions/DECISIONS.md` and
  `docs/adr/` first, and don't re-decide a resolved row.
- If the answer has to come from the user (a requirement, a preference, a detail the
  brief and the repo don't settle), **use the `grilling` skill** to ask, rather than
  guessing (§6). Record the answer as a row in `DECISIONS.md` before writing the code.
- If a design decision has two or more defensible answers, that's a `ponytail` moment
  (§6). Significant ones become an ADR (`docs/adr/NNNN-*.md`, from `0000-template.md`).
- When something breaks, append it to `docs/failure-log.md` as it happens. Engineering
  note Q7 ("the failure") cannot be written retroactively.
- Diagnose cluster problems in this order, always: `kubectl get pods` → `kubectl describe
  pod` (read Events) → `kubectl logs` (add `--previous` for a crashed container). Check
  the §9 traps table in the brief before inventing a theory.
- If you're about to touch code your session didn't write, check for
  `docs/handover/HANDOVER-<branch>.md` first. It may say "do not touch." Ownership split:
  Dev 1 owns the RAG pipeline and eval (`indexer/`, `api/app/{retrieval,providers,
  services}`, `eval/`, `corpus/`). Dev 2 owns the platform (Dockerfiles, `k8s/`,
  `.github/workflows/`, Makefile additions). Each partner does one real task in the other's
  area.
- Reference brief sections in commits and branches:
  `feat(api): refuse readiness on embedding-model mismatch (§4.4)` and
  `feat/s4.4-embed-pin`.

## 6. Skill invocations

This project uses three Claude Code skills. `caveman` and `ponytail` are **mandatory** at
fixed points, and a small task is not a reason to skip one. `grilling` is **recommended**,
and you use it whenever you need requirements or details from the user.

| Skill | Status | Fires when | Input | Must produce | Fails if |
|---|---|---|---|---|---|
| **`caveman`** | Mandatory | Start of every phase, before writing any code | The brief sections the phase delivers (`§N.N`), plus the matching starter-kit `TODO(section)` markers (`grep -rn 'STARTER-[T]ODO'`) | A stripped task list: nouns and verbs only, every item completable in ≤90 min, each tagged with its `§N.N` | Any line contains "consider", "maybe", "as needed"; fewer than 5 items; a line doesn't start with a verb |
| **`ponytail`** | Mandatory | The moment a design decision has ≥2 defensible answers, mid-phase, whenever it happens (e.g. cache store, how the corpus reaches the Job, OCR engine, chunk unit) | The decision, plus the constraining brief sections and `DECISIONS.md` rows | A decision-record stub, which becomes a `DECISIONS.md` row, an ADR, or an `ENGINEERING-NOTES.md` paragraph | Fewer than 2 rejected alternatives named, or a rejection with no reason given |
| **`grilling`** | Recommended | Whenever a requirement, preference, or detail is needed from the user and the brief, STARTER.md, and `DECISIONS.md` don't already answer it (corpus choice, provider mode, ownership, an ambiguity in the brief, what "done" means for a task) | The open question(s) and what's already known | Answers from the user, recorded as `DECISIONS.md` rows before the code that depends on them | Not applicable as a gate. Misused if it asks something the brief or the repo already answers, or if an answer is acted on without being recorded |

**Rules for using them:**

1. **Do not skip `caveman` because you already know the tasks.** What gets checked is the
   stripped task list itself, not your mental model of it.
2. **`ponytail` fires the moment the fork appears, not in end-of-phase cleanup.** If you
   notice mid-implementation that you're choosing between two designs, stop and invoke
   it there. Where the brief demands a measurement (chunk config, cache threshold,
   relevance floor), the stub records the alternatives and the numbers that decided them.
3. **Prefer `grilling` to guessing.** If proceeding means assuming something only the user
   can tell you, grill instead of picking silently. If the user is unavailable and the
   step is reversible, proceed on the most likely reading, record the assumption in
   `DECISIONS.md` as `ASSUMED`, and grill when they're back. Don't use it for questions
   the docs already answer.
4. **Pre-PR hardening review (mandatory, no skill).** Before opening a PR, review the full
   diff against `dev` yourself and produce ≥3 concrete findings with `file:line`: error
   paths, timeouts, resource cleanup, probe behaviour, limits, edge cases the happy path
   skipped. Each one becomes a commit or a documented `WONTFIX`. If you honestly find
   nothing, state why that is credible for *this specific diff*. A rubber stamp doesn't
   count.
5. **Log every skill invocation in `docs/AI-USAGE.md` at the moment it happens**, not
   reconstructed later from memory, `grilling` included whenever it is used. Format:
   ```markdown
   ## <date> · <branch>
   - **Tool:** Claude Code + `<skill>`
   - **Shaped / Wrote:** <what it touched>
   - **I changed:** <what you overrode or rejected and why, citing a §N.N or DECISIONS row if one applies>
   ```
   The "I changed" line is mandatory even when you accepted the output as-is. In that
   case write "accepted as-is" rather than omitting the line. Specific disclosure carries
   no penalty. Presenting AI work as your own is plagiarism under the course policy (§8).
6. **PR review is done by the partner, never by you on your own PR.** Your pre-PR review
   doesn't replace the partner's substantive review comment. "LGTM" is not a review.

## 7. Before you say a task is done

Run through this, out loud, not just in your head:

- [ ] Does anything under `api/` write to Chroma or run indexing? (§1.3)
- [ ] Can the indexer and the API still disagree about `EMBED_MODEL` without the API
      going not-ready? (§1.4)
- [ ] Can any citation reach the user that isn't in `retrieved`? Can a must-abstain
      question be answered? (§1.5–1.6)
- [ ] Can any model or provider failure become a 5xx, or get cached? (§1.7, §1.9)
- [ ] Did I add anything to a metric label, log line, or response body that could be a
      secret or unbounded cardinality?
- [ ] Does every new container have requests, limits, and the security context, in
      namespace `rahbar`, behind a NetworkPolicy allow rule? (§1.11–1.16)
- [ ] Did I write a test that I confirmed would fail without the implementation?
- [ ] Do `make test`, `make lint`, `make check`, and
      `kustomize build k8s/overlays/prod | kubeconform -strict` pass?
- [ ] If I touched manifests or the README: does the README apply order still work from a
      clean clone on a fresh `make cluster`? (−5)
- [ ] Is any number (resources, chunk size, threshold, floor) unbacked by committed
      evidence or a measurement table?
- [ ] Would this trip any row in the deduction ledger (§2)?
- [ ] Am I about to commit directly to `main`?
- [ ] Is every commit and PR authored by the user's configured account, with no Claude
      co-author trailer, session link, or "Generated with Claude Code" line? (§1.23)
- [ ] Did `caveman` run at the start of this phase, `ponytail` at every design fork, and
      the pre-PR hardening review before this PR? Was `grilling` used wherever I needed
      something from the user? Is each one logged in `docs/AI-USAGE.md`?

If any answer is "yes" where it shouldn't be, fix it before reporting completion. Don't
report the task as done and mention the caveat afterward.

## 8. Log every completed task in `docs/AI-USAGE.md`

After you complete a task, append one entry to the `## Task log` section of
`docs/AI-USAGE.md` before you report completion. Keep it to 1–2 lines: what you did and
which files it touched, with the `§N.N` it delivers. Format:

```markdown
- <date> · <branch> · <what was done, 1–2 lines>
```

This is separate from the per-skill entries required by §6 rule 5. Both go in the same
file. A task with no entry is an undisclosed AI contribution.
