# traces/: trace records from the cluster (RAGOps D, F4, R5)

Copied from the `ragops-results` volume after the minikube run of 2026-11-28
(`kubectl cp rahbar/ragops-shell:/results/traces ./traces`). One file per api or
api-candidate pod and day, one JSON line per query, with the full prompt and evidence
(ADR 0005). Read them with:

    python scripts/trace_show.py <trace_id> --dir traces
    python scripts/trace_summary.py --dir traces [--since ... --until ...]

369 queries: the four cluster suite runs on api-candidate, the hand-asked questions on
the live api, the release and undo, and an 82-question burst (summary:
eval/results/f/15-trace-summary-all.txt).

| trace id | what it shows | evidence file |
| --- | --- | --- |
| 61e8b56d9fcc44279126db019e3e63b3 | old-version question: superseded filter widened, 2023 and 2026 rules tied at 0.668, answer mixes both (a D5 candidate) | eval/results/f/06-trace-show.txt |
| 4e47cca292854a0486b1f3ca91553165 | abstention: nothing above the 0.65 floor, no prompt | 04-questions.jsonl |
| fa250ca558ef4366a827d66dcc74c6fe | injection in the question, flagged | 04-questions.jsonl |
| 8db3b24762574cfa8a61430ca90abe5a | cache hit | 04-questions.jsonl |
| c6954502fc314c94b687f099c62138fd | D4, rail in flag mode: b09 flagged, the planted claim repeated with a real citation | 11-d4-flag-mode.txt |
| 3186f723eafb46e084edd6229ce066fd | D4, rail in redact mode: b09 redacted, the model declines | 13-d4-redact-mode.txt |
| 7b68eca8b048d459429b204a682a6ba4 | after the k6 release: rahbar-k6, top_k 6 | 14-release-rollout.txt |
| b182e41b88f019409de08efb03476430 | the bad release: rahbar-minilm, all-minilm 1b226e2802db, dimension 384 | 14-release-rollout.txt |
| 13679ec44dc15adcc4652cd935fa48aa | after `rollout undo`: rahbar-k6, nomic-embed-text 0a109f422b47 | 14-release-rollout.txt |

The 46 fallbacks at 10:47-10:49 UTC are the first k6 and minilm suite runs, made before
llama3.2:3b had finished downloading: every generation call failed and the api returned
the canned answer, never a 5xx. Those two runs were discarded and re-run; their traces are
kept because they show the fallback path working.
