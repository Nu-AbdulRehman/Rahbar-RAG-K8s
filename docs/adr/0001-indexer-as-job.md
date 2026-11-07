# ADR 0001: The index is built by a Job, never by the API

## Status
Accepted · 2026-11-07

## Context
RAHBAR has two kinds of work. Building the index means downloading nine documents,
OCR-ing 41 scanned pages, chunking them into 803 pieces and embedding every piece. On our
minikube that takes about 190 seconds and peaks at 1659m CPU and 1159Mi of memory
(docs/evidence/kubectl-top.txt). Answering a question means one embedding, one Chroma
query and one model call; the api peaked at 6m CPU and 105Mi while answering 40 questions
(same file). The first kind of work is needed when the documents change. The second is
needed on every request.

The obvious design runs the indexing in the api's startup. We run three api replicas
against one Chroma volume, so that design fails in four ways:

- **Concurrent writers.** All three pods would start indexing at once and write into the
  same collection, each part way through a different document. The result is an index no
  single run produced, and no log tells you so.
- **Every restart pays again.** A rolling update, an OOM kill, a node drain or a failed
  liveness probe would each trigger the whole three-minute extraction and embedding run,
  on the pod that is supposed to be serving.
- **Readiness becomes false either way.** If the pod reports ready before the index is
  complete, users get answers from half an index. If it waits, a three-minute startup
  overruns the startup probe (30 x 2 s in k8s/base/api.yaml:40-43), the kubelet kills it,
  and a rollout replaces three working pods with three that never finish.
- **Changing the documents means a redeploy.** A new handbook would need a new api
  rollout, which ties content changes to code releases.

## Decision
A Kubernetes Job is the only writer to Chroma: `indexer` in k8s/base/indexer.yaml:7, with
`restartPolicy: OnFailure` (line 18) and `backoffLimit: 2` (line 12). A weekly CronJob,
`reindex` (line 62), runs the same image, command and arguments, with
`concurrencyPolicy: Forbid` (line 68) so two writers never overlap. Re-indexing without a
redeploy is one command:

```bash
kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar
```

The api opens the collection read-only (api/app/retrieval/chroma.py) and never creates,
adds to or deletes from it; no Chroma write method appears under api/. Its readiness probe
(`/readyz`, api/app/routes/health.py:22) returns 503 until the collection exists and is
non-empty, so a pod started before the first index is withheld from the Service instead
of serving empty retrievals.

What a run does, in order: fetch the corpus into an emptyDir and refuse to continue if any
file's SHA-256 differs from corpus/MANIFEST.md (decision Q4); extract, clean, chunk,
embed; upsert into the live collection and then delete ids that no longer exist; record
the embedding model and dimension in the collection metadata; bump the cache generation
in Redis so no answer from the old index is served (§3.3).

## Options considered
- **Index in the api's startup or lifespan.** Rejected for the four reasons above.
- **An init container on the api Deployment.** Still runs once per pod, so three replicas
  still race and every restart still re-indexes. It moves the problem, it does not
  remove it.
- **A sidecar or a single "leader" api pod that indexes.** Needs leader election for a
  task that runs a few times a month, and a writer inside the serving path.
- **Delete and recreate the collection on every run** (instead of upsert then prune).
  There would be a window with an empty collection, during which every api pod fails
  readiness at once and the Service has no endpoints. Upsert-then-prune keeps the old
  chunks answering until the new ones land.
- **A new collection per run, switched by name.** Chroma 1.0 has no alias, so the api
  would need to discover the new name. Not worth it for a weekly job.

## Consequences
- Indexing and serving scale and fail separately. The Job gets 1280Mi requested and a
  1792Mi limit; the api keeps a 160Mi request and does not carry indexing memory.
- A failed run fails loudly: a zero-chunk document, a hash mismatch, an Ollama error or a
  Redis failure exits non-zero, and the Job retries up to twice. Because the store step is
  idempotent, a retry is safe.
- A Job's pod template is immutable, so `kubectl apply -k` after editing the indexer
  fails until the old Job is deleted (`kubectl delete job indexer -n rahbar`). Day-to-day
  re-indexing uses the CronJob command above and never hits this (docs/failure-log.md).
- Watch: re-indexing shares the Ollama host with the api, so a question asked during a
  run can wait behind the embedding batches (docs/failure-log.md, first row). The
  CronJob runs on Sunday at 03:00 for that reason.
