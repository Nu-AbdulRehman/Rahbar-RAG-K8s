# Handover: Dev 1 branches, 2026-11-07

## Position
Dev 1 phases D1-P1 to D1-P6 are committed locally on seven stacked branches. Each one
starts from the previous one, and none is pushed or merged yet:

```
dev
 └ feat/s2-corpus                  D1-P1 corpus, MANIFEST, CORPUS.md (the first PR names the corpus)
    └ feat/s5-eval-harness         D1-P2 golden.yaml, run_eval.py scoring and gate
       └ feat/s3.1-indexer         D1-P3 extract, clean, chunk, embed, store, invalidate, fetch --out
          └ feat/s3.4-grounded-generation   D1-P4 retrieval, providers, abstention, retry, citations
             └ feat/s3.2-conversation-history   D1-P4b ADR 0002, history API, UI, follow-ups
                └ feat/s3.3-semantic-cache       D1-P5 ADR 0003, Redis cache, /readyz
                   └ feat/s4.8-observability     D1-P6 metrics and log line (this branch)
```

Open the PRs into `dev` in that order. Run the pre-PR hardening review on each diff first
(CLAUDE.md §6 rule 4); it has not been done for any of them yet.

## Green
- api: 55 tests, coverage 96 %; indexer: 40 tests; eval: 5 tests. ruff and mypy are clean.
- `scripts/check_submission.py` sections B, C, E and F pass. D fails only on the embedding-pin
  guard (Dev 2's swap task, below).
- Store checked by hand against a local chromadb 1.0.12 server: the dummy index is rebuilt
  into the real one, a re-run is safe, stale chunks are pruned, and `where={"superseded": False}`
  works.

## Half-done or blocked
- **Fixture baseline** (`eval/fixtures/baseline.fixture.json`): needs real embeddings
  (nomic-embed-text). Ollama is not installed on this machine. Create it from the first
  green e2e-eval run, or locally once Ollama is running. Never take it from the stub.
- **D1-P7 measurements** (three chunk configs, the relevance floor, the cache threshold,
  eval/baseline.json): need Ollama and the cluster. `RELEVANCE_FLOOR=0.5` and
  `CACHE_THRESHOLD=0.95` in api/app/config.py are make-dev placeholders (DECISIONS D19).
- **D1-P8** (FAILURE-ANALYSIS.md, ENGINEERING-NOTES Q5/Q6): wait on the P7 numbers and the pin
  guard.
- **e2e-eval CI job** (Dev 1's swap task): waits on Dev 2's Dockerfiles, manifests and ci.yml.
- **UI**: script syntax checked with node, but nobody has clicked through it in a browser yet.

## For Dev 2
- **Pin guard (your swap task):** `indexer/pipeline/store.py` already writes `embed_model` and
  `dimension` into the collection metadata (D16, ASSUMED: please confirm). Left for you: the
  startup comparison in `api/app/main.py` (STARTER-TODO 4.4) and a `pin` entry in
  `api/app/routes/health.py` `readyz`, which already returns 503 naming Chroma or Redis.
- **New ConfigMap keys** (every one needs a source comment): `RELEVANCE_FLOOR`,
  `CACHE=redis`, `CACHE_THRESHOLD`, `CACHE_MAX_ENTRIES`, `REDIS_HOST`, `REDIS_PORT`,
  `REDIS_TIMEOUT_SECONDS`, `HISTORY_TURNS`, `LLM_TIMEOUT_SECONDS`, `EMBED_TIMEOUT_SECONDS`
  (api); `EMBED_BATCH_SIZE`, `EMBED_TIMEOUT_SECONDS`, `OCR_DPI`, `REDIS_HOST`, `REDIS_PORT`
  (indexer). `CACHE` defaults to `none`, so set it to `redis` on the cluster.
- **Indexer image:** build context = repository root (it needs `corpus/fetch.py`,
  `corpus/sources.yaml`, `corpus/MANIFEST.md`). The only extra system package is
  `tesseract-ocr`: pdf2image and poppler were dropped (D12). Job and CronJob command:
  `python corpus/fetch.py --out /corpus && python corpus/fetch.py --verify --out /corpus && python -m pipeline.run`,
  with an emptyDir at `/corpus` and `CORPUS_DIR=/corpus`. CI runs `python -m pipeline.run` with
  `CORPUS_DIR=eval/fixtures`.
- **Indexer egress:** nu.edu.pk on 443, chroma, redis (the last step bumps the cache
  generation, and the Job fails if Redis is down), and the Ollama host.
- **CI coverage:** `pytest-cov==7.1.0` is now in api/requirements-dev.txt;
  `pytest --cov=app --cov-fail-under=60` passes.

## Literal next command
```
git switch feat/s2-corpus && git diff dev --stat     # start the pre-PR review of the first PR
```

## What will bite
- This machine has no `make`. Use `.venv/Scripts/<tool>` directly. tesseract lives in
  `C:\Program Files\Tesseract-OCR`, so put it on PATH before running OCR.
- The root `CLAUDE.md` and `AGENTS.md` (moved from docs/ in the working tree, not committed)
  contain the literal text "STARTER-TODO", which `make check` section 0 counts.
- The prospectus PDF is three-column and extracts interleaved (PIPELINE.md, "Could not
  recover"). Do not tune against it.
