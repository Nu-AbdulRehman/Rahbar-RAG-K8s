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
