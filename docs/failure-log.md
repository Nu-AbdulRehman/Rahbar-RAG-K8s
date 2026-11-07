# Failure log

Appended when something breaks, not afterwards. Feeds engineering note Q7.

| Date | Symptom | Cause | Fix |
| --- | --- | --- | --- |
| 2026-11-07 | Embedding one question timed out (httpx.ReadTimeout after EMBED_TIMEOUT_SECONDS=10) while a chunk-config re-index was embedding 550 chunks | Indexer and api share one Ollama host (D2). Ollama queued the single question behind the indexer's 32-text batches | Expected behaviour, not a fix: the api turns the timeout into the canned answer, never a 500. On the cluster, run re-indexes off-peak (the weekly CronJob), and watch rahbar_fallbacks_total{reason="retrieval"} during a reindex |
| 2026-11-07 | First real question took 2 min 12 s; the log showed `provider call failed ... ReadTimeout` on attempt 1 | llama3.2:3b loads into the GPU on the first call, which took longer than LLM_TIMEOUT_SECONDS=120. Attempt 2 answered in 8 s | The single retry absorbed it. On the cluster, warm the model before traffic (one `ollama run llama3.2:3b ""` on the host), or keep it loaded with OLLAMA_KEEP_ALIVE |
| 2026-11-07 | The same answer said "2.00" with a valid citation but `answered_from_context: false`, so the UI would show "Not covered" | The prompt only said when to set the flag false, and the 3B model read it as optional | Rule 2 of the instructions now defines the flag both ways (api/app/services/prompt.py) |
