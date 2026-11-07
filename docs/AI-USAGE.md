# AI usage

| Tool | What it wrote or shaped | What we changed afterwards, and why |
| --- | --- | --- |
| Claude Code | Dev 1 pipeline work; each change is listed in the logs below | Recorded per entry below |

## Skill log

## 2026-11-07 · feat/s2-corpus
- **Tool:** Claude Code + `caveman`
- **Shaped / Wrote:** D1-P1 task list: pick nine documents (§2); fetch them and write MANIFEST (§2); verify SHA-256 hashes (§2); prove scans with font lists (§2); write CORPUS rows (§2); record superseded flags (§3.1).
- **I changed:** accepted as-is.

## Task log

- 2026-11-07 · feat/s2-corpus · Seeded DECISIONS.md, failure-log.md and the handover folder so Dev 1 work can record decisions (D2-P1 had not landed); chose the corpus in corpus/sources.yaml (§2).
- 2026-11-07 · feat/s2-corpus · Ran fetch.py for all nine documents, confirmed `--verify` passes 9 of 9, committed corpus/MANIFEST.md (§2).
