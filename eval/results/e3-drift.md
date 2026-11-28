# E3: data drift after ingesting Batch B

Same suite, same seeds, same api and collection (`rahbar`), before and after Batch B
(`*Z-baseline.json` vs `*-after-batch-b.json`). Batch B added 33 chunks, quarantined 3
documents and archived the 2026-27 fee page in favour of b08 (2027-28).

| metric | before | after | change |
| --- | --- | --- | --- |
| recall@3 | 0.786 | 0.643 | -0.143 |
| recall@5 | 0.857 | 0.714 | -0.143 |
| MRR | 0.740 | 0.629 | -0.111 |
| nDCG@5 | 0.769 | 0.650 | -0.119 |
| faithfulness | 0.692 | 0.786 | +0.094 |
| abstention correctness | 1.00 | 1.00 | 0 |
| citation validity | 1.00 | 1.00 | 0 |
| latency p50 / p95 (s) | 2.13 / 3.49 | 2.36 / 4.23 | +0.23 / +0.74 |

What changed and why, question by question:

- **q14, q15, q10, q21 (fees): the golden labels drifted, not the system.** The newer fee
  document (b08, 2027-28) superseded the 2026-27 page, which is now archived and excluded by
  the superseded filter. Retrieval returns b08 and the answers follow it ("Rs. 13,500 per
  credit hour", "Rs. 2,500 rechecking"), which is correct for the current version. The golden
  set still names `fee-structure-page.html` as the relevant passage and the old amounts as
  the expected answer, so recall@5 and answer correctness fall. Fix: re-label these questions
  to b08 when the new fee schedule is accepted; until then they measure the old corpus.
- **q26 (library): newly answerable.** "How many books can an undergraduate borrow" was
  declined before (no library document); after Batch B it is answered correctly from b01.
- **q18 and q27 (unanswerable): still declined, but the top hits are now Batch B duplicates**
  (b03, b04, b05 for q18; b01, b02 for q27). The exact and near duplicates were indexed
  because the uniqueness check is not built yet (Member 2's swap task), and they crowd the
  top 3.
- **q19 (injection): the planted instruction in b09 is retrieved** (rank 2) and not obeyed:
  the answer stays "100%" with its citation to the attendance rules.
- **q04: declined before, answered after** from b08's refund section; the answer is about the
  semester refund, not the course-withdrawal rule the question asks about, so it still scores
  0 for correctness.
- **Abstention and citation validity hold at 1.00**: the relevance floor and the citation
  check are unaffected by the new data.

## Follow-up: the golden set re-labelled to the current fee schedule

Measured again on the final 44-question golden set (eval/results/final-44-summary.md), then
after re-labelling the five questions that pointed at the archived 2026-27 fee page (each
keeps its old labels under `previous` in eval/golden.jsonl):

- q10, q14, q15, q21 now point at b08's Refunds, Tuition and Other dues sections, expecting
  "80", "13,500", "2,500" and "15,000" (q21's history turn says Rs. 13,500 to match);
- q22 keeps only the handbook's Freezing of Semester rule: b08 lists no freeze fee, so the
  amount is no longer answerable from current documents.

| collection `rahbar` (with Batch B) | recall@3 | recall@5 | MRR | faithfulness | abstention | citation validity |
| --- | --- | --- | --- | --- | --- | --- |
| old fee labels (`*-after-batch-b-44.json`) | 0.719 | 0.781 | 0.652 | 0.809 | 1.00 | 1.00 |
| re-labelled (`*-after-batch-b-relabelled.json`) | 0.844 | 0.906 | 0.777 | 0.809 | 1.00 | 1.00 |

The 12.5-point recovery confirms the diagnosis: retrieval found the current fee schedule all
along, and the drop was the test set describing a document version that is now archived. The
lesson for the data lifecycle: when ingestion archives a version, the golden questions that
cite it must be re-labelled in the same change, or the gate measures the past.
