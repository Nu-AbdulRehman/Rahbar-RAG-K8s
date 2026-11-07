# Decisions

The resolution log. A decision the brief does not dictate gets a row here. Never re-decide a resolved row.

| # | Decision | Status | Rule it implies |
| --- | --- | --- | --- |
| D1 | LLM provider is ollama-host (llama3.2:3b, host.minikube.internal:11434) | Resolved | hosted is a working one-file swap; stub is used in every test and CI unit run |
| D2 | Embeddings are nomic-embed-text through the same Ollama host | Resolved | EMBED_MODEL is one ConfigMap key read by api and indexer |
| D3 | Semantic cache is Redis | Resolved | Deployment + PVC, ClusterIP only; defended in an ADR |
| D4 | Local cluster is minikube with Calico, metrics-server and ingress | Resolved | namespace rahbar; host rahbar.local |
| D5 | CI clusters are kind | Resolved | e2e-eval uses eval/fixtures with its own baseline; never mixed with the real baseline |
| D6 | Docs are a small set | Resolved | The required docs, ADRs 0001-0004, evidence/, this file |
| D7 | Dev 1 owns RAG and eval; Dev 2 owns Dockerfiles, k8s, workflows, Makefile additions | Resolved | Each dev does one real swap task |
| D8 | Git identity is the user's own account only | Resolved | No AI attribution in git metadata; disclosed only in docs/AI-USAGE.md |
| D9 | Images pinned; ours tagged by commit SHA | Resolved | chromadb/chroma:1.0.12 matches chromadb-client==1.0.12 |
| D10 | Conversation history lives in the browser | Resolved | The API uses it for follow-ups and context and stores nothing; ADR required |
| Q1 | Swap tasks: Dev 1 builds e2e-eval, Dev 2 builds the embedding-pin guard | Resolved | See the plan's swap table |
| Q3 | CI embeds with Ollama on the runner (nomic-embed-text only), LLM_PROVIDER=stub | Resolved | |
| Q4 | Documents reach the Job through fetch.py at start-up into an emptyDir, verified against MANIFEST.md | Resolved | CI overrides CORPUS_DIR to the fixtures |
| Q5 | Absent topic is hostel rules | Resolved | The Transport and Hostel Facilities PDF is excluded |
| Q6 | Bonus scope deferred until the project is complete | Deferred | No ollama-incluster or BM25 until then |
| D11 | The Aug 2023 rules PDF downloaded, so no substitute version pair is needed | Resolved | 2023-08 (superseded) vs 2026-06 |
| D12 | OCR: tesseract through pytesseract, pages rendered by pypdfium2 | Resolved (ponytail) | Rejected: pdf2image, which needs poppler as a second renderer when pdfplumber already ships pypdfium2; easyocr, which pulls in torch (about 2 GB of image) for typed text tesseract already reads; ocrmypdf, which needs ghostscript and rewrites the PDF. Dockerfile needs tesseract-ocr only |
| D13 | PDF text through pdfplumber, cropped to the page box, headings from font size | Resolved (ponytail) | Rejected: pypdf, which cannot crop and returns the facing page's text, so every handbook clause appears twice; pypdfium2 text, which has no per-character font size to find headings |
| D14 | Chunk unit is the word (whitespace token); CHUNK_SIZE counts the heading line too | Resolved (ponytail) | Rejected: characters, which cut words in half and do not give the token-based storage amplification §3.1 asks for; the embedding model's own tokenizer, which would tie chunking to one EMBED_MODEL, so changing the model would also change the chunks |
| D15 | Re-index upserts into the live collection, then deletes stale ids; rebuild only when the pinned model or dimension changes | Resolved (ponytail) | Rejected: delete and recreate on every run (the dummy index does this), which leaves an empty or missing collection while the API is serving, so readiness drops for every pod; a new collection per run swapped in by name, which Chroma 1.0 cannot alias, so the API would need to learn the new name. Checked against a local chromadb 1.0.12 server |
| D16 | The indexer writes embed_model and dimension into the collection metadata (indexer/pipeline/store.py pin_metadata) | ASSUMED | store.py needs the pin to decide when to rebuild, so the write side landed with D1-P3. Dev 2's swap task keeps the API side: compare at startup, /readyz 503 naming both values. Confirm with Dev 2 |
