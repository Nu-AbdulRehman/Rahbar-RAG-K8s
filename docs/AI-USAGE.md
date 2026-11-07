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
- **Shaped / Wrote:** OCR engine (D12), PDF extraction library (D13), chunk unit (D14).
- **I changed:** accepted as-is. pdf2image was dropped from indexer/requirements.txt because nothing uses it.

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
