# C2: the release gate on the C1 candidates

`scripts/gate.py` with `config/gate.yaml`, baseline `20261128T082600Z-baseline-44.json`
(rahbar-base: 150/30, nomic-embed-text, top_k 5). Inputs are Member 1's local C1 runs on
the 44-question golden set (`eval/results/final-44-summary.md`); the cluster re-runs go
beside these once the eval Job runs (F2).

| candidate | change | recall@5 drop | faithfulness | p95 s | p50 ratio | decision | file |
| --- | --- | --- | --- | --- | --- | --- | --- |
| k6 | top_k 6 | 0.000 | 0.733 | 12.54 | 1.004 | **pass** (release) | gate-k6.txt |
| minilm | all-minilm embeddings | 0.094 | 0.750 | 3.37 | 0.025 | **fail** (recall@5) | gate-minilm.txt |
| c200 | chunks 200/40 | 0.047 | 0.733 | 20.56 | 0.979 | **fail** (recall@5) | gate-c200.txt |
| o40 | overlap 40 | 0.063 | 0.812 | 5.37 | 0.922 | **fail** (recall@5) | gate-o40.txt |

Exit codes: 0 for k6, 1 for the other three. Release decision (Part C): release top_k 6
(R10b); reject all-minilm, which is also the deliberately bad release for `rollout undo`
(F3). all-minilm passes every latency rule only because most of its questions are declined
under a relevance floor calibrated for nomic-embed-text (final-44-summary.md): the recall
rule is the one that catches it.
