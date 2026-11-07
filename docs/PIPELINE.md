# Indexing and retrieval pipeline

<!-- STARTER-TODO(3.1, 3.3, 5.2): the chunking table and the cache thresholds are measured on the cluster (D1-P7); fill them, then delete this comment. -->

`python -m pipeline.run` runs extract, clean, chunk, embed and store, then expires the semantic cache. Numbers below are from the real corpus (9 documents, `corpus/MANIFEST.md`) at CHUNK_SIZE=400, CHUNK_OVERLAP=50, on 2026-11-07.

## Corpus delivery to the Job

Decision Q4: the Job downloads the corpus at start-up into an `emptyDir`, checks every file against the committed `corpus/MANIFEST.md`, and only then indexes. The PDFs never enter git or the image. The Job's command:

```sh
python corpus/fetch.py --out /corpus &&
  python corpus/fetch.py --verify --out /corpus &&
  python -m pipeline.run          # CORPUS_DIR=/corpus
```

- `--out /corpus` writes the files, `_index.json` and a throw-away MANIFEST into the emptyDir. The committed MANIFEST is never rewritten in the pod.
- `--verify --out /corpus` exits 1 if any SHA-256 differs, so the Job fails instead of indexing a document nobody reviewed. Checked by appending one byte to a copy of `grading-page.html`: "8 of 9 match the manifest", exit 1.
- The image therefore needs `corpus/fetch.py`, `corpus/sources.yaml` and `corpus/MANIFEST.md` (build context = repository root), plus egress to nu.edu.pk on 443. The Aug 2023 rules URL was moved from http to https so 443 is enough. Both HTML pages hashed the same on two downloads, so they are stable enough to pin.
- CI sets `CORPUS_DIR=eval/fixtures` and runs `python -m pipeline.run` alone.

## Extraction

pdfplumber, every page cropped to its page box (`indexer/pipeline/extract.py`). Headings are lines set at least 1.5 pt above the document's body size, or numbered title-like lines in the body font ("5. Unacceptable Uses of Generative AI Tools"). HTML pages become `# heading` lines and `| cell | cell |` table rows.

**Needed OCR** (no text layer, tesseract at 300 dpi): all 8 pages of `faculty-entrepreneurship-and-technical-start-ups-policy.pdf`, 24 of 26 pages of `undergraduate-academic-rules-aug-2023.pdf`, and the cover and blank pages of the two handbooks (5 and 4 pages). 41 pages in total.

**The trap we found:** the handbook PDFs hold the facing page's text at negative x. Without the crop, clause 1.21 appears on both page 10 and page 11, and every clause would be retrieved twice. pypdf's text extraction returns it twice; cropping to the page box removes it.

**Before and after, one table** (grade points, the same rule in three documents):

| Source | What extraction produced |
| --- | --- |
| 2023 rules, OCR'd scan | `Bo (3.00 [D {100 \| \|B [267 [F000 \|`: most rows lost and the columns unreadable |
| 2026 handbook, text layer | `Grade Points Grade Points A+ 4.00 C+ 2.33 A 4.00 C 2.00 ...`: a two-column table read across, but each grade still sits next to its points |
| `grading-page.html` | `\| B+ \| 3.33 \| Very Good \|`: one row per line, columns intact |

**Could not recover:**
- The 2023 rules' grade table. The current value is in the handbook and on the grading page, and the 2023 file is superseded anyway.
- The three-column layout of `prospectus-2026-academic-rules-and-regulations.pdf`. pdfplumber reads its lines across the columns ("1. Attendance Requirement 4. Semester Course Load"), so its 13 chunks mix clauses. The same rules are in the handbook, cleanly.
- OCR noise on the start-ups policy's cover and form pages.

## Cleaning

`indexer/pipeline/clean.py`, per document:

1. Running headers and footers: a line whose letters (digits and spaces ignored) repeat on at least 40 % of pages in a document of 4 or more pages. Ignoring spaces catches the handbook footer that the text layer spells "U ndergraduate Academic Rules and Regulations 2026 11".
2. Lines that are only a page number ("17", "IV", "1 0").
3. Contents entries: any line with dot leaders, and lines ending in a page number on a page titled "Contents" or "Table of Contents". Otherwise the contents page would win the retrieval for every heading it lists.
4. The byte-order mark at the top of the HTML pages, and runs of blank lines.

**Deliberately not stripped:** clause numbers ("1.21", "5.4", and the lone "6.2" lines that OCR separates from their text). They look like layout noise, but they are the exact terms a student asks about.

## Chunking

Unit: words (whitespace tokens), decision D14. CHUNK_SIZE counts the heading line that starts every chunk. Splitting order: section (heading), then paragraph (blank line, clause number, list marker or table), then sentence or table row, then fixed word windows for a sentence longer than a chunk. Chunks never cross a section, and overlap repeats the last CHUNK_OVERLAP words of the previous chunk in the same section.

At 400/50: **550 chunks**, 67,229 words after cleaning, 67,811 stored. **Storage amplification 1.009**. Most sections are shorter than 400 words, so overlap and repeated headings add little. The amplification is in the Job's `chunking done` log line.

| Size (words) | Overlap (words) | recall@5 | Chunks stored |
| --- | --- | --- | --- |
| 400 | 50 | measured in D1-P7 | 550 |

## Embedding

Model `EMBED_MODEL` from the ConfigMap (nomic-embed-text, decision D2), through Ollama's `POST /api/embed` in batches of `EMBED_BATCH_SIZE`. The dimension is whatever the model returns; nothing in the code names a model or a dimension. `store.py` writes `embed_model` and `dimension` into the collection metadata (D16). A model or dimension change rebuilds the collection; an ordinary re-index upserts and prunes (D15), so the API never sees an empty collection.

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
