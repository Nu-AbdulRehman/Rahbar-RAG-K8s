# Indexing and retrieval pipeline

`python -m pipeline.run` runs extract, clean, chunk, embed and store, then expires the semantic cache. Numbers below are from the real corpus (9 documents, `corpus/MANIFEST.md`) and `eval/golden.yaml`, measured on 2026-11-07 with chromadb 1.0.12 and Ollama 0.40.15 (nomic-embed-text, llama3.2:3b) on a laptop GPU. The cluster runs the same images and models, so the numbers carry over; re-measure if either model changes.

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

Six configurations, each indexed into its own collection and scored on the 16 golden questions that have relevant passages (retrieval only, top_k 5). Raw numbers, per question: `docs/evidence/tuning-chunks.json`.

| Size (words) | Overlap (words) | recall@3 | recall@5 | Chunks stored | Storage amplification |
| --- | --- | --- | --- | --- | --- |
| 800 | 100 | 0.781 | 0.781 | 517 | 0.985 |
| 400 | 50 | 0.781 | 0.781 | 549 | 1.009 |
| 200 | 40 | 0.781 | 0.844 | 676 | 1.084 |
| **150** | **30** | **0.844** | **0.938** | **803** | **1.123** |
| 100 | 20 | 0.844 | 0.906 | 1,105 | 1.184 |
| 100 | 0 | 0.938 | 0.938 | 1,009 | 1.010 |

**Shipped: 150/30.** It ties the best recall@5 (0.938) with a fifth fewer chunks than 100/0, and each passage the model sees is half as long again. The overlap means a sentence cut at a chunk boundary still appears whole in one of the two neighbours, which matters for the Generative AI policy's long definitions (corpus property 5). Storage amplification is 1.123: about 75,500 stored words for 67,229 cleaned words, from the overlap plus the heading every chunk repeats.

What the table says: the large chunks lose q03 ("passed its prerequisite") and q08 (literature reviews), because a 400-word "Scheduling of Classes" chunk or Generative AI chunk averages its meaning across five rules, and the specific one stops winning. Smaller chunks give each rule its own vector. Breaking stage B on purpose (100 words, no overlap) does **not** hurt recall here, because every chunk still carries its section heading; see FAILURE-ANALYSIS.md. One question is 6.25 points of recall@5 at this size of golden set, so 0.906 against 0.938 is a single question.

## Embedding

Model `EMBED_MODEL` from the ConfigMap (nomic-embed-text, decision D2), through Ollama's `POST /api/embed` in batches of `EMBED_BATCH_SIZE`. Vector dimension 768, as nomic-embed-text returns it; nothing in the code names a model or a dimension. `store.py` writes `embed_model` and `dimension` into the collection metadata (D16). A model or dimension change rebuilds the collection; an ordinary re-index upserts and prunes (D15), so the API never sees an empty collection.

How the api checks the pin: the startup comparison and the `/readyz` refusal are Dev 2's swap task, not built yet. Until then, a mismatch in dimension surfaces as `InvalidArgumentError` on every query and the canned answer (FAILURE-ANALYSIS.md, stage C).

## Store

`indexer/pipeline/store.py` is the only code that writes to Chroma. It writes one collection, `CHROMA_COLLECTION` (default `rahbar`). The last run, on 2026-11-07 at 150/30, stored **803 chunks**:

| Document | doc_version | Superseded | Pages | OCR'd pages | Chunks |
| --- | --- | --- | --- | --- | --- |
| `undergraduate-academic-rules-aug-2023.pdf` | 2023-08 | yes | 26 | 24 | 55 |
| `academic-rules-handbook-jun-2026.pdf` | 2026-06 | no | 58 | 5 | 99 |
| `prospectus-2026-academic-rules-and-regulations.pdf` | 2026 | no | 5 | 0 | 36 |
| `student-handbook-jun-2026.pdf` | 2026-06 | no | 64 | 4 | 117 |
| `annual-report-2019-20.pdf` | 2019-20 | no | 33 | 0 | 95 |
| `annual-report-2023-24.pdf` | 2023-24 | no | 85 | 0 | 357 |
| `fee-structure-page.html` | 2026-27 | no | 1 | 0 | 10 |
| `grading-page.html` | 2026 | no | 1 | 0 | 11 |
| `faculty-entrepreneurship-and-technical-start-ups-policy.pdf` | 2022-05 | no | 8 | 8 | 23 |

**Per chunk** (`indexer/pipeline/models.py`, `Chunk`):

| Field | Type | Example | Used for |
| --- | --- | --- | --- |
| id | str | `academic-rules-handbook-jun-2026.pdf#0012` | Stable: same document and position, same id, so a re-index upserts in place |
| document | str | `Attendance Requirements\n1.21 Students are required ...` | The text, with its section heading as the first line |
| embedding | list[float] | 768 floats | Similarity search |
| source | str (metadata) | `academic-rules-handbook-jun-2026.pdf` | Citations, recall matching |
| section | str (metadata) | `Attendance Requirements` | Citations, recall matching |
| page | int (metadata) | `10` | Citations (PDF page, 1-based; 1 for HTML and Markdown) |
| doc_version | str (metadata) | `2026-06` | Telling versions apart |
| superseded | bool (metadata) | `false` | The default `where={"superseded": False}` filter |

**Per collection:** `hnsw:space: cosine` (so the api's score is 1 - distance), `embed_model` and `dimension`, the embedding pin.

## Relevance floor

The top similarity of every golden question on the shipped 150/30 index (`docs/evidence/relevance-floor.txt`): the four must-abstain questions (hostel rules, plus the injection that asks about them) top out at **0.600**, and the lowest answerable question scores **0.695** (q06, B+ grade points).

| RELEVANCE_FLOOR | Must-abstain answered | Answerable declined |
| --- | --- | --- |
| 0.60 | q18 (curfew, 0.6001) | none |
| 0.62 | none | none |
| **0.65** | **none** | **none** |
| 0.70 | none | q06 |

**Shipped: 0.65**, the middle of the 0.600 to 0.695 gap, so either side has about 0.05 of margin. On the CI fixtures the abstain question scores 0.472 and the lowest answerable one 0.660, which is close to the floor: if e2e-eval ever fails f06 on recall alone, look here first.

## Semantic cache

Cosine similarity between the 16 question pairs in `eval/cache_pairs.yaml`, written before measuring: 7 paraphrases that may share a cached answer, and 9 near misses that must never hit (`docs/evidence/cache-threshold.txt`).

| CACHE_THRESHOLD | False hits | Paraphrases that hit |
| --- | --- | --- |
| 0.90 | 3 | 3 of 7 |
| 0.95 | 1 | 2 of 7 |
| **0.96** | **0** | **1 of 7** |

**The false hit that ruled out 0.95:** "How much of the fee is refunded if I leave within the first 15 days of classes?" against the same question with "30 days", at 0.9517. Those answers are 80 % and 50 %. At 0.90 the campus transfer fee also hit the temporary campus transfer fee (0.909), and the undergraduate warning CGPA hit the MS one (0.904). **Shipped: 0.96**, the lowest threshold tried with zero false hits. It is deliberately conservative: only near-verbatim repeats hit (the generative-AI paraphrase at 0.967), because the embedder barely tells numbers apart, and a cached wrong fee is served to everyone.

## Generation and the baseline

`eval/results.json` and `eval/baseline.json` come from `python eval/run_eval.py --api http://localhost:8000 --update-baseline` against the api with RETRIEVER=chroma, LLM_PROVIDER=ollama-host (llama3.2:3b), the 150/30 index, RELEVANCE_FLOOR 0.65 and TEMPERATURE 0.2: recall@3 0.844, recall@5 0.938, citation validity 1.00 (13 citations), abstention correctness 1.00. By type, recall@5: ordinary 1.00, version 1.00, injection 1.00, exact 0.667, follow-up 0.50 (not gated).

The fixture baseline `eval/fixtures/baseline.fixture.json` was taken the way CI runs (decision Q3): fixtures indexed at 150/30 with nomic-embed-text, LLM_PROVIDER=stub. Recall@5 1.00, citation validity 1.00, abstention 1.00.

The first real run surfaced two generation faults, both now fixed and logged in docs/failure-log.md: llama3.2:3b miscopied citation fields ("1.2 Academic Year" for "Academic Year"), and once marked a correct answer as `answered_from_context: false`. Each evidence passage now ends with the exact citation JSON to copy, and a reply marked not-from-context always shows the standard decline instead of the model's own text. Invalid replies went from 4 to 0 in a run of 22 questions. The model still declines 5 answerable questions (q03, q04, q07, q08, q13). That costs helpfulness, not grounding, and the gate does not score it.

## Evaluation method

`eval/run_eval.py` matches by **(source, section)**, never by chunk id: chunk ids change every time the chunk size changes, and the golden set has to survive the three chunking runs unchanged. A section matches after lower-casing, straightening curly quotes, collapsing whitespace and dropping trailing punctuation, so "Academic Warning/Probation" in the golden set matches the same heading from a PDF text layer.

- **recall@k**: relevant (source, section) pairs found in the top k retrieved, divided by the relevant pairs. Must-abstain questions have none and are left out of the mean. Reported at k=3 and k=5, overall and by question type.
- **Citation validity**: citations whose (source, section, page) all match a passage in that response's `retrieved` list, pooled over every citation in the run.
- **Abstention correctness**: must-abstain questions answered with `answered_from_context: false`, divided by the must-abstain questions.
- **Gate** (§5.4): fails if recall@5 is more than 5 points below the baseline, if any must-abstain question is answered, or if citation validity is under 95 % (or there are no citations to score). Exit codes: 0 pass, 1 gate failed, 2 not implemented.

Follow-up questions (type `followup`, ADR 0002) carry a `history` list that run_eval.py sends with the question. They are reported under `by_type.followup` but left out of the overall recall, citation validity and abstention numbers, so the gate stays comparable with baselines taken before history existed.

The real golden set uses `eval/baseline.json`; the CI fixture set uses `eval/fixtures/baseline.fixture.json`. `make eval-fixtures` passes the fixture baseline explicitly, so the two are never mixed.

Harness check against `make dev` with stubs, 2026-11-07: exit 1, as expected. The stub retriever never returns fixture passages and the stub provider answers everything, so recall@5 is 0.0, abstention correctness 0.0 and citation validity 1.0. Output: `docs/evidence/eval-fixtures-stub.txt`. That run was not used as a baseline, because a stub baseline would set the recall floor to zero. The fixture baseline was taken later with the real retriever (see "Generation and the baseline").

## Configuration for the cluster

The values below are measured or justified above. They go into the `rahbar-config` ConfigMap with these comments. Every other key has a working default in `api/app/config.py` and `indexer/pipeline/config.py`.

```yaml
CHUNK_SIZE: "150"              # words; best recall@5 of 6 configs (PIPELINE.md "Chunking")
CHUNK_OVERLAP: "30"            # words; same table
TOP_K: "5"                     # top_k 1 drops recall@5 from 0.938 to 0.656 (FAILURE-ANALYSIS C)
RELEVANCE_FLOOR: "0.65"        # between must-abstain max 0.600 and answerable min 0.695
CACHE: "redis"                 # the code default is none, for make dev
CACHE_THRESHOLD: "0.96"        # lowest with zero false hits; 0.95 hit "15 days" on "30 days"
TEMPERATURE: "0.2"             # facts and JSON need 0-0.3 (startup refuses more); 0 invalid replies in 22
EMBED_MODEL: "nomic-embed-text"  # D2; the pin, read by api and indexer
LLM_MODEL: "llama3.2:3b"       # D1
LLM_TIMEOUT_SECONDS: "60"      # per call; REQUEST_BUDGET_SECONDS bounds the whole request
REQUEST_BUDGET_SECONDS: "50"   # below nginx-ingress's 60 s proxy-read-timeout, so no 504 reaches users
```

The api also reads `REDIS_HOST`, `REDIS_PORT`, `REDIS_TIMEOUT_SECONDS`, `CACHE_MAX_ENTRIES`, `HISTORY_TURNS` and `EMBED_TIMEOUT_SECONDS`. The indexer reads `EMBED_BATCH_SIZE`, `EMBED_TIMEOUT_SECONDS`, `OCR_DPI`, `REDIS_HOST` and `REDIS_PORT`. Their defaults suit the cluster.

**What the indexer image and Job need:**
- Build context = repository root, for `corpus/fetch.py`, `corpus/sources.yaml` and `corpus/MANIFEST.md`.
- The only system package is `tesseract-ocr` (D12).
- The command and the `/corpus` emptyDir are in "Corpus delivery to the Job" above.
- Egress to nu.edu.pk on 443, to chroma, to redis (the last step bumps the cache generation, and the run fails without it), and to the Ollama host.

A cold llama3.2:3b load can take longer than the request budget. The first question after a deploy then gets the canned answer, while the model finishes loading for the next one. Warm the model on the host before a demo.
