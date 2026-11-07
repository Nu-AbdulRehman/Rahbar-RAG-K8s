# Indexing and retrieval pipeline

<!-- STARTER-TODO(3.1, 3.3, 5.2): fill each section with your numbers, then delete this comment. -->

## Extraction
Which documents needed OCR, one before-and-after example of a table, what could not be recovered.

## Cleaning
The rules you applied, and one thing you deliberately did not strip.

## Chunking
Size and overlap you shipped, storage amplification (stored tokens / original tokens),
and the three configurations you measured:

| Size (tokens) | Overlap (tokens) | recall@5 | Chunks stored |
| --- | --- | --- | --- |

## Embedding
Model, vector dimension, where the pin lives, how the API checks it.

## Semantic cache
Thresholds you tried, the false hit that ruled one out, the one you shipped.

## Evaluation method

`eval/run_eval.py` matches by **(source, section)**, never by chunk id: chunk ids change every time the chunk size changes, and the golden set has to survive the three chunking runs unchanged. A section matches after lower-casing, straightening curly quotes, collapsing whitespace and dropping trailing punctuation, so "Academic Warning/Probation" in the golden set matches the same heading from a PDF text layer.

- **recall@k**: relevant (source, section) pairs found in the top k retrieved, divided by the relevant pairs. Must-abstain questions have none and are left out of the mean. Reported at k=3 and k=5, overall and by question type.
- **Citation validity**: citations whose (source, section, page) all match a passage in that response's `retrieved` list, pooled over every citation in the run.
- **Abstention correctness**: must-abstain questions answered with `answered_from_context: false`, divided by the must-abstain questions.
- **Gate** (§5.4): fails if recall@5 is more than 5 points below the baseline, if any must-abstain question is answered, or if citation validity is under 95 % (or there are no citations to score). Exit codes: 0 pass, 1 gate failed, 2 not implemented.

The real golden set uses `eval/baseline.json`; the CI fixture set uses `eval/fixtures/baseline.fixture.json`. `make eval-fixtures` passes the fixture baseline explicitly, so the two are never mixed.

Harness check against `make dev` with stubs, 2026-11-07: exit 1, as expected. The stub retriever never returns fixture passages and the stub provider answers everything, so recall@5 is 0.0, abstention correctness 0.0 and citation validity 1.0. Output: `docs/evidence/eval-fixtures-stub.txt`. The fixture baseline is written only when the real indexer and retriever run on the fixtures, because a baseline taken from the stub would set a recall floor of zero.
