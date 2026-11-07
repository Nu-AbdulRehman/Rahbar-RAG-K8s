# Engineering notes

<!-- STARTER-TODO(7): Q1-Q4 and Q7 are Dev 2's (platform) and still open. Q5 and Q6 are
     answered below. Delete this comment when all seven are written. -->

## 1. Indexing in API startup: what breaks with 3 replicas and one Chroma volume?

## 2. Readiness and liveness swapped, Chroma slow for 90 seconds: what happens?

## 3. What does a CPU-based HPA measure on a generation service, and what should scale it?

## 4. The indexer's peak memory, its limit, the margin, and the exit code when it is wrong

## 5. recall@5 by question type: where is it worst, and why?

From eval/results.json (llama3.2:3b, 150/30 index): ordinary 1.00, version 1.00, injection
1.00, **exact term 0.667**, and follow-up 0.50 (ungated). Exact term is the worst gated type,
and one question accounts for all of it: q13, "What does clause 1.21 of the academic rules
require?" (eval/golden.yaml:106). Its top hits are the Student Handbook's "I - ACADEMIC
RULES and REGULATIONS" (0.736), the Prospectus title section and the handbook cover. The
right chunk, "Attendance Requirements", starts with the literal text "1.21 Students are
required to maintain 100% attendance" and is not in the top 5 at any of the six chunk
sizes we measured (docs/evidence/tuning-chunks.json).

Why: an embedding encodes what text is about, and "clause 1.21" carries almost no meaning
beyond "a rule in the academic rules". The vector for the question lands near every chunk
about academic rules in general, and the token "1.21", the only thing that identifies the
answer, has close to no weight. The same blur shows up in the cache measurement: "15
days" and "30 days" in otherwise identical questions score 0.952 (docs/PIPELINE.md,
"Semantic cache"). Exact identifiers are where dense retrieval is weakest.

The RAG lecture's fix is **hybrid retrieval**: run a lexical BM25 search beside the vector
search and merge the two rankings (reciprocal rank fusion). BM25 scores "1.21" as a rare
exact token and would rank the "Attendance Requirements" chunk first. A cheaper partial
fix would be to pull clause numbers into chunk metadata at indexing time and filter on them
when the question contains one. Hybrid BM25 is the deferred bonus (decision Q6), so we
report the gap instead of hiding it.

The follow-up type's 0.50 has a different cause: q22 ("What about if I freeze the semester
instead?") is retrieved as the previous question plus this one (api/app/services/
conversation.py, `retrieval_query`), and the previous question, about withdrawal, pulls
"Withdrawal from a Course" to the top. ADR 0002 names an LLM rewrite as the upgrade if this
matters.

## 6. EMBED_MODEL changed on the API only: what does your system do?

Measured on 2026-11-07 (docs/FAILURE-ANALYSIS.md, stage C): we switched the api to
all-minilm (384 dimensions) against an index built with nomic-embed-text (768).

**Without the guardrail** (today's api, where the pin check is still being built):
1. The api embeds each question with the new model (api/app/retrieval/chroma.py:39).
2. Chroma rejects the query: `InvalidArgumentError: Collection expecting embedding with
   dimension of 768, got 384`.
3. The service catches it (api/app/services/answer.py:71-74), logs `retrieval failed`,
   counts `rahbar_fallbacks_total{reason="retrieval"}` and returns the canned answer.
   No 500, but every user gets "could not produce a reliable answer".
4. `/readyz` (api/app/routes/health.py:20) still says ready, because Chroma is reachable
   and the collection is non-empty, so all three pods stay in the Service and serve
   nothing but fallbacks.

That is the lucky case. Two models with the **same** dimension would raise nothing at all:
Chroma would return its nearest vectors from a different embedding space, scores would
still look plausible, the relevance floor would let some through, and the model would be
handed unrelated passages. Without a guard, nothing anywhere would turn red.

**With the guardrail:** the indexer writes `embed_model` and `dimension` into the collection
metadata whenever it stores (indexer/pipeline/store.py:28-32). It also rebuilds the
collection rather than mixing vectors when they change (store.py:53). At startup the api
compares that metadata with its own EMBED_MODEL and, on a mismatch, keeps `/readyz` at 503
with one log line naming both models. The pods sit at 0/1 READY, the old ReplicaSet keeps
serving during a rollout because of `maxUnavailable: 0`, and the fix is either reverting
the ConfigMap or re-indexing with the new model. The api-side check is Dev 2's swap task
(api/app/main.py:40); its file and line will be added here when it lands.

## 7. The failure that cost us more than an hour
