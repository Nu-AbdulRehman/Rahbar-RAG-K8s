# Corpus

Source: FAST-NUCES public website (nu.edu.pk), public pages only. Documents: 9 (7 PDFs and 2 HTML pages). Pages: 279 PDF pages, plus the 2 HTML pages.

The PDFs are not committed. `corpus/MANIFEST.md` records each URL and SHA-256; `python corpus/fetch.py` downloads the same files and `python corpus/fetch.py --verify` checks the bytes. The list lives in `corpus/sources.yaml`.

| # | Required property | Document(s) that provide it | Evidence or notes | Failure mode reachable |
| --- | --- | --- | --- | --- |
| 1 | At least 6 documents, 40 pages | All nine | Handbook 58, Annual Report 2023-24 85, Student Handbook 64, Annual Report 2019-20 33, 2023 rules 26, start-ups policy 8, Prospectus rules 5 | Sets the scale |
| 2 | Two versions of one policy | `undergraduate-academic-rules-aug-2023.pdf` (`doc_version` 2023-08, superseded) and `academic-rules-handbook-jun-2026.pdf` (`doc_version` 2026-06, current) | Same clause scheme with real changes: clause 1.6 went from "15/16 weeks of teaching" to "16 weeks of teaching, one makeup week", and the minimum CGPA for graduation moved from clause 1.26 to 1.25 | E, outdated source |
| 3 | Scanned, image-only PDF | `faculty-entrepreneurship-and-technical-start-ups-policy.pdf`, all 8 pages. Also `undergraduate-academic-rules-aug-2023.pdf`, 24 of 26 pages | `pdffonts` was not available on the development machine, so we read the same data with pypdf: the policy has no `/Font` resource on any page and an image on all 8. The 2023 rules have fonts only on pages 1 and 26 | A, bad extraction |
| 4 | A table with real information | `fee-structure-page.html` (tuition, miscellaneous fees, refund timeline); `grading-page.html` (grade points, minimum CGPA by programme) | Refund timeline: 100% to day 10, 80% to day 15, 60% to day 20, 50% to day 30, none after. The Annual Reports add PDF tables | A, jumbled columns |
| 5 | Long definitions | `student-handbook-jun-2026.pdf`, pages 48 to 57 | The Generative AI policy runs over ten pages with numbered sub-sections, longer than a fixed-size chunk | B, poor chunks |
| 6 | A deliberately absent topic | Hostel rules. The prospectus's Transport and Hostel Facilities PDF is excluded | A student would plausibly ask about hostel fees or how to apply. The corpus only says hostels exist: Student Handbook pages 44-45 and Annual Reports (campus descriptions), with no rules, fees or application steps | Abstention |
| 7 | Exact-term content | `academic-rules-handbook-jun-2026.pdf` clause 1.21 (page 10) and clause 5.4 (page 24); `fee-structure-page.html` (Rs. 12,000 per credit hour, Rs. 30,000 admission fee) | Clause numbers, CGPA thresholds and fees | Embeddings blur exact terms |

Page numbers are PDF page numbers, starting at 1.

## How versions are marked

`doc_version` and `superseded` are set by hand in `corpus/sources.yaml`, because only a person can decide that one document replaces another. `corpus/fetch.py` copies them into `corpus/raw/_index.json`, `discover()` in `indexer/pipeline/run.py` reads that file, and every chunk carries both fields into Chroma.

Only the 2023 rules are `superseded: true`. The Annual Reports are also dated, but each one reports its own year rather than replacing a policy, so they stay `superseded: false`. The Prospectus rules are a current 5-page summary of the same policy with different clause numbers (attendance is clause 1 there), so they also stay current.

## Traps in the source files

- The handbook PDFs repeat text across neighbouring pages: clause 1.21 of the 2026 handbook has a text layer on both pages 10 and 11. Extraction has to deal with this or retrieval returns duplicates.
- The fee page's tuition table is labelled "w.e.f. Fall 2026 semester", so it can go stale. MANIFEST.md's hash shows when the page changes.
