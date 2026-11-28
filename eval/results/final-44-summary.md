# Part B and C1 on the final golden set (44 questions)

All runs on 2026-11-28 with eval/golden.jsonl at 44 questions (18 answerable, 12 unanswerable,
14 hard; 8 written by hand), seed 42, Ollama on the laptop GPU, Chroma in Docker. The
pre-Batch-B collections are `rahbar-base` (baseline, 150/30, nomic-embed-text), `rahbar-k6`,
`rahbar-c200`, `rahbar-o40` and `rahbar-minilm`; `rahbar` holds the corpus plus Batch B (E3).
These supersede the 36-question runs earlier in this folder.

| run | collection | recall@3 | recall@5 | MRR | nDCG@5 | recall@5 typos | cos gap | faithfulness | abstention | citation validity | p50 s | p95 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline-44 | rahbar-base | 0.625 | 0.688 | 0.569 | 0.600 | 0.656 | 0.392 | 0.714 | 1.00 | 1.00 | 2.43 | 6.69 |
| k6-44 | rahbar-k6 | 0.625 | 0.688 | 0.569 | 0.600 | 0.656 | 0.392 | 0.733 | 1.00 | 1.00 | 2.79 | 32.47 |
| k6-44-isolated | rahbar-k6 | 0.625 | 0.688 | 0.569 | 0.600 | 0.656 | 0.392 | 0.733 | 1.00 | 1.00 | 2.44 | 12.54 |
| c200-44 | rahbar-c200 | 0.562 | 0.641 | 0.552 | 0.572 | 0.609 | 0.392 | 0.733 | 1.00 | 1.00 | 2.38 | 20.56 |
| o40-44 | rahbar-o40 | 0.547 | 0.625 | 0.544 | 0.556 | 0.609 | 0.392 | 0.812 | 1.00 | 1.00 | 2.24 | 5.37 |
| minilm-44 | rahbar-minilm | 0.578 | 0.594 | 0.562 | 0.566 | 0.594 | 0.585 | 0.750 | 1.00 | 1.00 | 0.06 | 3.37 |
| after-batch-b-44 | rahbar | 0.719 | 0.781 | 0.652 | 0.686 | 0.734 | 0.392 | 0.809 | 1.00 | 1.00 | 2.47 | 12.41 |

**Why recall is lower than on 36 questions.** Seven golden questions (q26, q28-q31, q35, q36)
are answered by Batch B documents, which
the pre-Batch-B collections do not hold, so every pre-Batch-B run scores 0 on them; the
after-Batch-B run scores them, which is most of its higher recall.

**C1 decision data (R10b).** k6 keeps the baseline's retrieval exactly (recall@5 0.688, MRR
0.569): one more passage does not change the top five. Every chunking change and all-minilm
lose recall@5 by more than 2 points: c200 -4.7, o40 -6.3, minilm -9.4.

**all-minilm's fast answers are declines.** Its median latency of 0.06 s is not speed: the
mean top-1 similarity with all-minilm is 0.582, below the relevance floor of 0.65 that was
measured for nomic-embed-text (D19), so most questions are declined before any generation
(12 of 44 answered, baseline 14). The floor is a property of the embedding model and has to be
re-measured with it.

**Latency: p50 is reliable here, p95 is not.** Medians stay at 2.4-2.8 s in every run. The
p95 values swing between 3.4 s and 32 s on the same code: the slowest requests took 30-50 s
while generating at most 278 tokens from about 1,500 (about 5 s of GPU work), and the Ollama
server log shows its prompt-cache restore stalling for up to 7.2 s at a time; a few requests
ran past the api's 50 s request budget and returned the canned answer. Re-running k6 with the
other five api processes stopped cut its p95 from 32.5 s to 12.5 s, so contention explains
part of it and the server stalls the rest. A latency gate should use cluster measurements
(Part F) or the median until then.

**Stochasticity (baseline-44, two seeded runs), non-zero differences:**
- module.embed_ms_per_chunk_mean: +3.77
- module.embed_ms_per_chunk_p95: +25.01
- end_to_end.latency_p50_s: -0.158
- end_to_end.latency_p95_s: -0.314
