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

## Task log

- 2026-11-07 · feat/s2-corpus · Seeded DECISIONS.md, failure-log.md and the handover folder so Dev 1 work can record decisions (D2-P1 had not landed); chose the corpus in corpus/sources.yaml (§2).
- 2026-11-07 · feat/s2-corpus · Ran fetch.py for all nine documents, confirmed `--verify` passes 9 of 9, committed corpus/MANIFEST.md (§2).
- 2026-11-07 · feat/s2-corpus · Wrote docs/CORPUS.md: one row per §2 property with document, page, evidence and failure mode.
- 2026-11-07 · feat/s2-corpus · Confirmed _index.json flags (only the 2023 rules are superseded), documented how the flag is set, added a discover() test (§3.1).
- 2026-11-07 · feat/s5-eval-harness · Wrote eval/golden.yaml: 20 questions (10 ordinary, 2 version, 3 exact, 3 abstain, 2 injection), sections taken from the document bodies (§5.1).
- 2026-11-07 · feat/s5-eval-harness · Implemented recall_at_k, citation_validity, summarise and gate in eval/run_eval.py, with eval/test_run_eval.py; `make test` runs it and `make eval-fixtures` uses its own baseline file (§5.2-§5.4).
- 2026-11-07 · feat/s5-eval-harness · Ran the fixture eval end to end against stubs (exit 1, as expected), recorded the evaluation method in PIPELINE.md; fixture baseline deferred until the real retriever runs (§5.4).
