# Failure analysis

Four stages broken on purpose, one at a time, on 2026-11-07 against the real corpus (150/30
index, nomic-embed-text, chromadb 1.0.12) and restored after each run. Raw output is in the
measurement scripts' results, summarised here. The order follows the RAG lecture's advice:
A to E first, because only F is the model's fault.

## Stage A · Extraction: the scanned PDF indexed without OCR
- **What we broke:** indexed every document with the OCR'd pages left empty, as if
  `ocr_page` (indexer/pipeline/extract.py:107) were never called for pages under
  `MIN_TEXT_CHARS` (extract.py:58).
- **Symptom:** the Faculty Entrepreneurship policy went from 23 chunks to 0, with no error
  anywhere. Asked "What does the policy count as faculty entrepreneurship?", retrieval
  returned the Annual Reports' "Services" sections at 0.648 instead of the policy's "Scope"
  at 0.839. The worst part: "Who can a faculty member be under the faculty entrepreneurship
  policy?" returned "Services" at **0.680, above the 0.65 relevance floor**, so the system
  would have answered confidently from the wrong document instead of abstaining.
- **Diagnosis, as if we had not caused it:** the indexer's per-document log line
  `"msg": "chunked", "source": "faculty-entrepreneurship-...pdf", "chunks": 0, "ocr_pages": 0`
  (indexer/pipeline/run.py). A document with pages but zero chunks is the signal. In the api,
  the request log line's `chunk_ids` never name that source for questions about it.
- **Remedy:** OCR is on for every textless page (decision D12). A Job that sees a document
  produce zero chunks should fail rather than log it. That is not built yet; it is the next
  guard worth adding.

## Stage B · Chunking: fixed 100-word chunks with no overlap
- **What we broke:** CHUNK_SIZE=100, CHUNK_OVERLAP=0, re-indexed.
- **Symptom:** none in recall. recall@5 stayed at 0.938, the same as the shipped 150/30, and
  recall@3 rose to 0.938 (docs/PIPELINE.md, "Chunking"). The break the brief predicts did not
  happen, and finding out why is the result: every chunk starts with its section heading
  (indexer/pipeline/chunk.py:82), and chunks never cross a section, so a 100-word piece of
  "Attendance Requirements" still says what it is about. What did change: 1,009 chunks
  instead of 803, and each evidence passage the model sees is a third shorter. That cut
  costs answers, not retrieval: a definition split across two chunks reaches the model in
  halves.
- **Diagnosis, as if we had not caused it:** recall@5 alone would not show it. The signals
  are the indexer's `chunking done` line (`chunks: 1009`, `storage_amplification: 1.01`)
  and, on the api side, answers whose single citation covers half a clause. The golden set
  would need a question whose answer spans a long definition to catch it in the gate.
- **Remedy:** ship 150/30 (D21). Overlap keeps a sentence cut at a boundary whole in one
  neighbour, and the heading prefix is what makes small chunks safe at all.

## Stage C · Retrieval: top_k 1, and EMBED_MODEL changed on the api only
- **What we broke (1):** TOP_K=1.
- **Symptom:** recall dropped from 0.938 (top 5) to **0.656** (top 1). Questions with two
  relevant sources (q01, q06, q07, q08: the handbook and the grading page or the Student
  Handbook) can score at most 0.5, and any question whose best chunk ranks second scores 0.
- **Diagnosis:** the request log line shows `"top_k": 1` and a single entry in `chunk_ids`;
  `make eval` shows recall@5 fall by about 28 points and the CI gate fails.
- **What we broke (2):** EMBED_MODEL=all-minilm on the api only, index still nomic-embed-text.
- **Symptom:** every question returned the canned "could not produce a reliable answer". Chroma
  raised `InvalidArgumentError: Collection expecting embedding with dimension of 768, got 384`,
  which the service turns into the fallback (api/app/services/answer.py:71-74) rather than a
  500. If the two models had the same dimension, nothing would have raised at all, and
  retrieval would have returned confident nonsense.
- **Diagnosis:** `rahbar_fallbacks_total{reason="retrieval"}` climbing with every request,
  and the `retrieval failed` warning on every request. With the embedding-pin guard the
  pod would instead stay 0/1 READY, with one log line naming both models (§4.4).
- **Remedy:** EMBED_MODEL is one ConfigMap key read by both programs. The indexer records it
  in the collection metadata (indexer/pipeline/store.py:28-32), and the api's startup check
  refuses readiness on a mismatch (Dev 2's guard, in progress).

## Stage E · Source: the superseded filter removed
- **What we broke:** retrieval with `include_superseded=True` for every question, as if
  api/app/retrieval/chroma.py:40 always passed `where=None`.
- **Symptom:** for q11 ("How many weeks of teaching does a regular semester have?") the
  repealed 2023 rules' "Academic Year" chunk ranked **first at 0.767**, just above the
  current 2026 chunk at 0.766, and 2023's "Normal Semester Course Load" took third place.
  The model would read "15/16 weeks" first; the current rule is "16 weeks of teaching, one
  makeup week". q12 (summer length) was unaffected, because the 2026 summer chunks
  outscored the OCR'd 2023 text. The two versions are near-identical text, so their
  similarities are within 0.001: ranking cannot separate them, only metadata can.
- **Diagnosis, as if we had not caused it:** the request log line's `chunk_ids` contain
  `undergraduate-academic-rules-aug-2023.pdf#...` while `include_superseded` is false. The
  answer's citation names the 2023 file in the UI. In eval, the version type's recall@5 is
  unchanged, because the 2026 chunk is still in the top 5. Recall cannot see this failure,
  which is why the filter is a hard rule and not a tuned number.
- **Remedy:** `where={"superseded": False}` by default (chroma.py:40), widened only when the
  question names an older version (api/app/services/query.py:15-24, decision D17). Version
  handling stays a metadata filter, never a prompt instruction.
