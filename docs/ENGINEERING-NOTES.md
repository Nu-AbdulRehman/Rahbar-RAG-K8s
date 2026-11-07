# Engineering notes

<!-- STARTER-TODO(7): Q7 (the failure) is still open; it is written last, from
     docs/failure-log.md. Delete this comment when it is. -->

## 1. Indexing in API startup: what breaks with 3 replicas and one Chroma volume?

**The failure: three concurrent writers on one collection.** With indexing in the
FastAPI lifespan, all three pods of `replicas: 3` (k8s/base/api.yaml:8) start at once and
each runs extract, chunk, embed and store against the same Chroma collection on the one
volume `data-chroma-0`. Our store step upserts every chunk and then deletes the ids its own
run did not produce (indexer/pipeline/store.py:61-65). Pod A, half way through, deletes
chunks that pod B has just written and A has not reached yet. The collection ends up with
a mix that no single run produced, and nothing fails, so nothing alerts. It also costs
more than correctness: the measured run takes about 190 s at 1659m CPU and 1159Mi
(docs/evidence/kubectl-top.txt), which is 9x the api's whole memory limit (320Mi,
api.yaml:63). The pods would be OOM-killed (exit 137) before they finished, and a 190 s
startup is past the startup probe's 60 s budget (30 x 2 s, api.yaml:40-43), so the kubelet
would kill them anyway. Every rollout, eviction or crash would start the race again.

**What prevents it:** the Job `indexer` (k8s/base/indexer.yaml:7) is the only writer. It
runs one pod (`restartPolicy: OnFailure`, line 18, `backoffLimit: 2`, line 12), and the
weekly CronJob that repeats it has `concurrencyPolicy: Forbid` (line 68), so there are
never two writers. Chroma itself is one StatefulSet pod with its own claim from
`volumeClaimTemplates` and `ReadWriteOnce` (k8s/base/chroma.yaml:59-63). The api only
reads: no Chroma write call exists under api/, and its readiness waits for a non-empty
collection instead (api/app/routes/health.py:29). ADR 0001 has the full reasoning.

## 2. Readiness and liveness swapped, Chroma slow for 90 seconds: what happens?

We ran it (docs/evidence/probes-chroma-down.txt): 3 api replicas, `chroma` scaled to 0
for 90 s, one `/api/ask` through the Ingress every ~8 s, first with the probes as shipped
and then with the two paths swapped.

**As shipped** (liveness `/healthz`, readiness `/readyz`, api.yaml:44-51): `/readyz` fails
on Chroma (health.py:29) and after 3 x 10 s all three pods go 0/1 and leave the Service.
The Ingress answers 503 straight away instead of letting requests hang. **No pod
restarts** (`r=0` throughout). When Chroma returns, the pods are ready again within one
probe period: 200 at t+106 s, 16 s after Chroma came back.

**Swapped** (liveness `/readyz`, readiness `/healthz`): the pods stay "ready" while Chroma
is down, so the Service keeps sending traffic to pods that cannot retrieve. Our first
answers were still 200 only because that question was in the semantic cache, which never
touches Chroma; an uncached question would have got the canned answer. After 3 x 20 s of
failed liveness, the kubelet **kills all three pods within about 10 s of each other**
(t+69 s to t+94 s, `r=1` on every pod), and the Ingress returns 502 and then 503. The
restart did nothing useful: the pods were never broken, Chroma was. If the outage had
lasted longer, every restart would have failed liveness again and the whole Deployment
would have gone into CrashLoopBackOff, with back-off delays that keep it down after
Chroma is back. A slow dependency would have become a cluster-wide outage. That is why
`/healthz` touches nothing (health.py:16) and the dependency checks live only in readiness.

One related bug found while building this: the Chroma client used to connect in the
lifespan, so a Chroma that was down at boot crashed every api pod at startup, the same
restart storm through a different door. It now connects on first use
(api/app/retrieval/chroma.py:25-37, docs/failure-log.md).

## 3. What does a CPU-based HPA measure on a generation service, and what should scale it?

It measures the pod's own CPU divided by its request (100m, api.yaml:59), and on a
generation service that is close to nothing. During a 40-question burst, 6 at a time,
with the cache mostly missed, the api pods peaked at **6m CPU** while answers took
**11.3 s at p50 and 30.8 s at worst**, and the HPA (api.yaml:88-97) read **4-6 % of its
70 % target** (docs/evidence/kubectl-top.txt). The pods spend nearly all of a request
waiting on two HTTP calls to Ollama (the embedding and the generation), and waiting costs
no CPU. So the HPA would never scale up, however long the queue got. Worse, scaling the
api would not help: the work happens in the single Ollama process on the host, which
answers one generation at a time, so eight api pods would queue on the same model.

**The signal that matters** is load relative to generation capacity: in-flight requests
per pod, or generation latency (p95 of `rahbar_generation_seconds`,
api/app/routes/metrics.py:26) against a target. **To use it** we would need (1) an
in-flight gauge in the api (we export latency histograms and counters, but no
concurrency gauge), (2) Prometheus scraping `/metrics`, (3) prometheus-adapter or KEDA to
serve it through the custom metrics API, and (4) an HPA on that `Pods` metric. Even then
it should scale the thing that generates: with Ollama in the cluster (the
`ollama-incluster` mode) the model servers are what the HPA should grow, and the api
should scale with them. CPU stays as a floor for the rare CPU-heavy path (JSON validation
of long answers).

## 4. The indexer's peak memory, its limit, the margin, and the exit code when it is wrong

`kubectl top pods` every 10 s during a full run (9 documents, 41 OCR pages, 803 chunks)
put the indexer's **peak at 1159Mi** and 1659m CPU (docs/evidence/kubectl-top.txt). The
peak is OCR: pages are rendered to images at 300 dpi before tesseract reads them
(indexer/pipeline/extract.py:61). Our values (k8s/base/indexer.yaml:42-48):

| | Value | Why |
| --- | --- | --- |
| request | 1280Mi | the peak plus 10 %, so the scheduler reserves what the run really uses |
| limit | 1792Mi | 1.5x the peak: a larger scanned document, or a higher OCR_DPI, still fits |
| margin | 633Mi (55 % over the peak) | |

**Set it wrong and the exit code is 137**: 128 + 9, the kernel's OOM killer sending
SIGKILL when the container passes its memory limit. We measured it
(docs/evidence/indexer-oom-137.txt): the same Job with `limits.memory: 768Mi` was killed
after 85 s with `reason: OOMKilled, exitCode: 137`, during OCR. Because the run had not
reached the store step, Chroma still held the previous 803 chunks: a failed index run
never leaves a half-written index. With the real Job's `restartPolicy: OnFailure` it
would have retried twice (`backoffLimit: 2`) and failed the same way each time, because
the input does not change; the fix is the limit, not the retries. CPU is different: above
the 2-CPU limit the indexer is throttled and only slower, never killed.

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
