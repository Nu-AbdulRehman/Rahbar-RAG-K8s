# Report sections: Member 1 (Nu-AbdulRehman)

Draft text for the report PDF (Part G): Parts A, B, C1, D5 and E, and Q4 (a), (b) and (d).
Every number links to a committed file. **Cluster** numbers come from minikube Jobs;
**local** numbers come from the laptop stack (Chroma in Docker, Ollama on the host GPU,
eval/results/final-44-summary.md). The golden set is the final 44 questions (18 answerable,
12 unanswerable, 14 hard; 8 written by hand, 8 synthetic reviewed by both members).
Trim to fit the 8 pages. Member 2's sections are in docs/report/member2-sections.md.

## A. Data management

**A1 verification** (`indexer/pipeline/verify.py`) runs after extraction and before
chunking. Each document gets pass or fail, with a reason, for quality, completeness,
recency and uniqueness. A quality, completeness or uniqueness failure moves it to
`quarantine/` with a `<file>.reason.json`, and it is not indexed. A recency failure
archives the older version, which stays indexed with `superseded: true`. Every run writes
`reports/verify-<run>.json`.

Batch B through the ingestion Job on the cluster (eval/results/f/09-batch-b-ingestion-job.txt):

| file | planted problem | failed check | action |
| --- | --- | --- | --- |
| b02-library-rules-copy.md | exact duplicate of b01 | uniqueness (same SHA-256) | quarantine |
| b04-exam-conduct-copy.md | exact duplicate of b03 | uniqueness (same SHA-256) | quarantine |
| b05-exam-conduct-revised-wording.md | near duplicate of b03 | uniqueness (cosine 0.9997 >= 0.98) | quarantine |
| b06-scholarship-policy-truncated.pdf | truncated PDF | quality (PdfminerException), completeness | quarantine |
| b07-transport-notice.md | missing title and version | completeness | quarantine |
| b11-scanned-notice-ocr.txt | scan with almost no text | quality, completeness | quarantine |
| b08-fee-structure-2027.md | newer version of the fee page | recency (on the 2026-27 page) | b08 indexed, 2026-27 page archived |
| b09-it-acceptable-use.md | injected instruction | none (by design) | indexed; the D4 rail redacts it at query time |
| b01, b03, b10, b12 | none | none | indexed |

**A2 incremental update** (`indexer/pipeline/store.py` `sync()`): every chunk carries a
`content_hash` and its `doc_id`. Only a new or changed hash is embedded, a flag change is a
metadata update, and ids that are no longer produced are deleted.

| run | embedded | metadata only | unchanged | deleted | evidence |
| --- | --- | --- | --- | --- | --- |
| first ingestion (cluster Job) | 803 | 0 | 0 | 0 | eval/results/f/01-ingestion-job-first-run.txt |
| unchanged corpus (cluster CronJob run) | **0** | 0 | 803 | 0 | eval/results/f/02-ingestion-unchanged-corpus.txt; Member 1's cluster: cluster-m1/02-unchanged-corpus.txt |
| two runs started together (cluster) | 0 and 0 | 0 | 803 | 0 | cluster-m1/09-two-runs-at-once.txt: the lake lock makes the second wait |
| Batch B (cluster Job) | 21 | 10 | 793 | 0 | eval/results/f/09-batch-b-ingestion-job.txt |
| one changed document (local) | 1 | 0 | 836 | 0 | eval/results/a/05-changed-document.txt |
| one deleted document (local) | 0 | 0 | 834 | 3 | eval/results/a/06-deleted-document.txt; `counts` shows 0 chunks for its doc_id (06-counts-after-delete.txt) |
| rollback to the 2026-27 fee page (local) | 0 | 10 | 824 | 0 | eval/results/a/07-rollback.txt |
| roll forward to 2027-28 (local) | 0 | 13 | 821 | 0 | eval/results/a/08-roll-forward.txt |

Rollback is `python -m pipeline.ops restore fee-structure-page 2026-27`. It moves the
archived version back to `raw/` and archives the current one, and the next run flips
`superseded` without re-embedding anything. The first attempt was re-archived by the next
run's recency check (eval/results/a/07a-rollback-bug-rearchived.txt). Recency now compares
only with current versions, and a test reproduces the bug.

## B. Offline testing at three levels

One command: `python eval/suite.py --api <url> --collection <name> --label <label>
[--runs 2]`. On the cluster: `kubectl apply -f k8s/eval-job.yaml`. It writes
`<UTC stamp>-<label>.json` with the summary table.

| level | metric | cluster baseline | local baseline |
| --- | --- | --- | --- |
| module | paraphrase / unrelated mean cosine (16 + 16 pairs) | 0.760 / 0.367 | 0.760 / 0.367 |
| module | gap | 0.393 | 0.392 |
| module | embedding time per chunk, mean (ms) | 74.8 | see summary |
| module | determinism, largest difference | 0.0 | 0.0 |
| component | recall@3 / recall@5 | 0.500 / 0.562 | 0.625 / 0.688 |
| component | MRR / nDCG@5 | 0.465 / 0.491 | 0.569 / 0.600 |
| component | recall@5 with typos (15 % of words, seed 42) | 0.547 | 0.656 |
| end-to-end | faithfulness (llama3.2:3b judge) | 0.786 (11 of 14) | 0.714 (10 of 14) |
| end-to-end | abstention correctness (12 unanswerable) | 1.00 | 1.00 |
| end-to-end | citation validity | 1.00 (20 citations) | 1.00 |
| end-to-end | latency p50 / p95 (s) | 2.24 / 7.03 | 2.43 / 6.69 |

Files: eval/results/cluster-m1/eval/20261128T133413Z-baseline-cluster.json (the eval Job,
`kubectl apply -f k8s/eval-job.yaml`, transcript cluster-m1/03-eval-job-baseline.txt) and
eval/results/20261128T*-baseline-44.json. Member 2's earlier cluster run
(eval/results/cluster/) has the same retrieval and abstention numbers.

- **Why cluster recall is lower.** The cluster runs use golden.jsonl after the E3
  re-labelling, which points five fee questions at the 2027-28 schedule from Batch B. The
  suite ran before Batch B was ingested, as the C1 comparison requires, so those questions
  cannot be found. Compare cluster runs with cluster runs only.
- **Noise test.** Typos cost 3.2 points of recall@5 locally and 1.5 on the cluster. On
  Member 2's cluster they gained 1.6 points, because a typo moved one query onto a better
  chunk. With 32 answerable questions one question is 3.1 points, so the noise test can't
  tell an effect that small from chance.
- **Judge agreement.** The judge matched our 8 hand labels 6 times out of 8 (75 %), with
  one error in each direction (eval/results/faithfulness-agreement.txt).
- **Stochasticity.** We fixed the Ollama seed (42), temperature 0.2 and Python `random`
  (the typo test), then ran the whole suite twice. Every retrieval, abstention, citation
  and faithfulness metric came out identical. Only timings moved: embedding time per chunk
  +5.63 ms, p50 +0.241 s, p95 +5.40 s on Member 1's cluster (Member 2's: -1.02 ms, -0.094 s,
  -0.163 s). The cause is load on the shared GPU and the HTTP path; that is the only
  remaining variation, and it is why the gate's p95 rule is absolute (25 s), not relative.
  Between the two laptops' clusters, with the same seed, a few individual answers differ
  (different GPUs: NVIDIA and AMD), while every retrieval metric agrees exactly.

## C1. One change: top_k 5 to 6

We chose the change by measurement (R10b). The plan's candidate, chunks of 200/40, lost
recall, and so did every other chunking variant:

| candidate | env | recall@5 | MRR | faithfulness | answered | p50 s | gate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline (150/30, nomic, top_k 5) | cluster | 0.562 | 0.465 | 0.786 | 14 | 2.24 | n/a |
| **top_k 6** | cluster | 0.562 | 0.465 | 0.714 | 14 | 2.44 | pass |
| all-minilm | cluster | 0.469 | 0.438 | 0.667 | 12 | 0.08 | **fail** |
| chunks 200/40 | local | 0.641 (base 0.688) | 0.552 | 0.733 | | 2.38 | fail |
| overlap 40 | local | 0.625 | 0.544 | 0.812 | | 2.24 | fail |

top_k 6 leaves the top five unchanged, so every retrieval metric is identical. The
difference is only at the end-to-end level: the prompt gets one more passage. Cluster rows
are the eval Job on Member 1's minikube (eval/results/cluster-m1/04, 05: gate FAIL for
all-minilm, recall@5 -9.4 points; gate PASS for k6). Compared question by question, on both
members' clusters, the change cost one answer and added two:

- **q41 (semester freeze), answered by the baseline, declined with k6.** In the trace, the
  ground-truth chunk is still rank 1. The sixth passage is only loosely related, and
  llama3.2:3b declined. We saw the same pattern after the live release: "What attendance
  is required to sit the final exam?" ranked the attendance chunk first (0.778), took a
  retake-examination passage sixth (0.656), and was declined (trace
  7b68eca8b048d459429b204a682a6ba4). A 3B model handles conflicting or diluted evidence by
  declining, which is the safe failure.
- **q26 (library loans) and q43 (CGPA below the minimum), declined by the baseline,
  answered with k6.** The extra passage gave the model something to answer from. q43's
  answer was judged unsupported on both clusters. q26's was judged unsupported on Member
  2's (the Student Handbook's 10 books, not Batch B's four) and supported on Member 1's.

Faithfulness falls from 11 of 14 to 10 of 14 (Member 1) or 10 of 15 (Member 2) judged
answers, inside the gate's one-judged-answer margin. The gate (Member 2's C2) passes it,
and we release it with that caution recorded.

## D5. Root cause from a trace only

The answer is Part B's q13, "What does clause 1.21 of the academic rules require?". It is an
exact-term question, it is declined in every run, and we read only its trace,
`7087caa6dc4949aea29a80263a9e8fb2` (baseline, `api-candidate`, collection `rahbar`):

1. Filters: `superseded: false`, relevance floor 0.65. The floor did not cause it, because
   all five chunks clear it (0.659 to 0.737).
2. Retrieved: student-handbook#0023 "I - ACADEMIC RULES and REGULATIONS" (0.737), the
   prospectus rules pages #0001-#0003, and the handbook's "June 2026" cover chunk #0001.
3. Missing: academic-rules-handbook-jun-2026.pdf#0014 "Attendance Requirements". It is the
   only chunk that contains the text "1.21", and it is not in the top 5.
4. Cause: the dense embedding matched "academic rules" to chunks that are about the rules
   in general. A clause number carries almost no meaning for nomic-embed-text, so the
   chunk that holds it never ranked. The model then declined correctly from the evidence
   it was given.
5. Fix: a lexical (BM25) score fused with the dense one for exact terms such as clause
   numbers and codes. A larger top_k doesn't help: with top_k 6 the sixth chunk is the
   front matter (trace fa54a26caf5f4c7ba0e0d714db976df2).

## E. Drift and coverage

- **E1** `eval/live_queries.jsonl`: 41 queries, 28 in the golden set's domain and 13 on
  topics the corpus or tests don't cover.
- **E2** `python eval/query_coverage.py`, or `kubectl apply -f k8s/coverage-job.yaml` on the
  cluster: the nearest golden question per live query, by cosine. We chose a threshold of
  0.65 from a sweep. At 0.65, 26 of 28 in-domain queries reach it and 2 of 13 off-topic
  ones do. At 0.80, only 10 of 28 in-domain queries would count as covered (0.27 overall,
  eval/results/20261128T071746Z-coverage-before-thr080-sweep.json). The check exits 1
  below 85 %.

| run | golden questions | covered | coverage | exit | evidence |
| --- | --- | --- | --- | --- | --- |
| before E4 (local) | 27 | 28 of 41 | 68 % | 1 | eval/results/20261128T071814Z-coverage-before.json |
| after 7 questions (local) | 34 | 34 of 41 | 83 % | 1 | ...-coverage-after.json |
| after E4, 9 questions (local) | 36 | 36 of 41 | 88 % | 0 | ...-coverage-after-e4.json |
| before E4 (cluster Job, `--without-category coverage_gap`) | 35 | 28 of 41 | 68 % | 1 (Job Failed) | eval/results/cluster-m1/06-coverage-before-e4.txt |
| after E4 (cluster Job) | 44 | 36 of 41 | 88 % | 0 (Job Complete) | eval/results/cluster-m1/07-coverage-after-e4.txt |

Before E4, 13 queries were uncovered: counselling, library, sports and transport (2
each), and attendance, cafeteria, course repeat, exam conduct and IT accounts (1 each).
E4 added nine golden questions from those topics (q28-q36, category `coverage_gap`).
Batch B's documents answer six of them, and three are unanswerable. Five queries are still
uncovered: attendance, course repeat, library, sports and transport (1 each).

- **E3 data drift** (eval/results/e3-drift.md). After Batch B, recall@5 on the collection
  with Batch B fell from 0.857 to 0.714. Retrieval did not change. Five golden questions
  still pointed at the 2026-27 fee page, which Batch B's 2027-28 schedule had superseded,
  and the superseded filter now excluded it. After re-labelling those five questions, recall@5 rose to 0.906
  (0.781 to 0.906 on the 44-question set). The lesson for the lifecycle: when ingestion
  archives a version, the golden questions that cite it must be re-labelled in the same
  change, or the gate measures the past.

## Q4

**(a) Which check caught the most, and what wasn't caught?** Uniqueness caught the most
problems, and it was the only check that failed for each of them. It quarantined three
documents: the two exact copies (b02, b04) and the near duplicate (b05, cosine 0.9997).
Completeness also failed three documents (b06, b07, b11), but two of those also failed
quality. Verification didn't catch the injected instruction in b09. It is well-formed,
complete, unique and current, so it was indexed, and only the D4 retrieval rail acts on it,
at query time. In flag mode the rail let "fees are waived" through with a valid citation,
and the cache then served it, which is why the cluster runs `redact`. Running the same
instruction-pattern rail (`api/app/services/guardrails.py`) as a fifth check at
verification would quarantine it before it is ever embedded.

**(b) Module looked fine, component didn't.** all-minilm has the better module-level
gap: 0.585 against nomic-embed-text's 0.393, because its unrelated pairs sit near 0.07. Yet
its recall@5 is 9.4 points lower (cluster 0.469 against 0.562; local 0.594 against 0.688),
and end to end it answers 11 or 12 questions (the two clusters) instead of 14. The gap measures how well the model
separates easy pairs. Retrieval needs the right chunk to beat near-misses from the same
handbook, and all-minilm's absolute similarities (top-1 mean 0.582) fall below a relevance
floor that was calibrated for nomic-embed-text. Its fast p50 (0.02 to 0.08 s) is declines, not
speed.

**(d) The metric we trust least: faithfulness.** The judge is the same 3B model that writes
the answers. It agreed with our hand labels 6 times out of 8, wrong once in each direction.
It sees every retrieved passage, not only the cited ones, which makes it lenient (the q12
case). It is computed over only 11 to 15 answered questions, so one verdict moves the score
by 7 points. The seeded runs agree exactly, but that shows the judge is repeatable, not
that it is right. It is why the gate's faithfulness floor is set one judged answer below
the baseline. Local p95 latency comes second: it swung from 3 s to 32 s on the same code,
because of Ollama's prompt-cache stalls.
