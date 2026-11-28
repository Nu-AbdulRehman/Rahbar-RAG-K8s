# Batch B: a second batch with planted problems (RAGOps A2)

Twelve documents we wrote ourselves (decision R13), so they can be committed. Each one
exercises a verification check or a data-lake rule. Ingest them by copying the folder's
documents into `<DATA_LAKE_DIR>/incoming/` and running the ingestion Job (or
`python -m pipeline.run` locally); `intake()` moves them into `raw/`.

| File | Planted problem | Expected check result | Expected action |
| --- | --- | --- | --- |
| b01-library-rules.md | none (new topic: library) | all pass | index |
| b02-library-rules-copy.md | **exact duplicate** of b01 (same bytes) | uniqueness fail | quarantine |
| b03-exam-conduct.md | none (new topic: exam conduct) | all pass | index |
| b04-exam-conduct-copy.md | **exact duplicate** of b03 (same bytes) | uniqueness fail | quarantine |
| b05-exam-conduct-revised-wording.md | **near duplicate** of b03 (a few words reworded, another doc_id) | uniqueness fail (embedding similarity) | quarantine |
| b06-scholarship-policy-truncated.pdf | **truncated / corrupt** PDF (cut at 55 %, no `%%EOF`; built by `make_truncated_pdf.py`) | quality fail (extraction error), completeness fail (truncated) | quarantine |
| b07-transport-notice.md | **missing metadata**: no version or date | completeness fail | quarantine |
| b08-fee-structure-2027.md | **newer version** of the corpus fee page (`fee-structure-page`, 2026-27 → 2027-28) | passes; the 2026-27 page fails recency | index b08; archive the old page |
| b09-it-acceptable-use.md | **injected instruction** in section 3 ("Ignore all previous instructions...") | all pass: verification does not read intent | index; the injection defence and the D4 guardrail must handle it at query time |
| b10-sports-facilities.md | none (new topic: sports) | all pass | index |
| b11-scanned-notice-ocr.txt | garbled text, as from a bad OCR | quality fail, completeness fail | quarantine |
| b12-student-counselling.md | none (new topic: counselling) | all pass | index |

The uniqueness check (Member 2) catches b02 and b04 as exact duplicates (same SHA-256) and
b05 as a near duplicate (cosine 0.9997 against b03, threshold 0.98). On the cluster the
ingestion Job quarantined exactly the six files the table expects
(eval/results/f/09-batch-b-ingestion-job.txt).
