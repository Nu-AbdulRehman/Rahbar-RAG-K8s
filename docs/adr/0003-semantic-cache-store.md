# ADR 0003: The semantic cache lives in Redis

## Status
Accepted · 2026-11-07 (decision D3, D1-P5)

## Context
§3.3 asks for a semantic cache: a new question whose embedding is close enough to an
answered one gets the stored answer without a retrieval or a generation call. It must be
shared by all api replicas (3 to 8 pods behind one Service), it must survive a pod
restart, and it must be emptied when the index is rebuilt, or the new index "answers
nothing" because the old answers keep being served. The brief allows Redis or a second
Chroma collection.

## Decision
Redis 7, a Deployment with a PVC and a ClusterIP Service (manifests by Dev 2), reached
only by the api and the indexer.

- **Entries:** one Redis list per cache generation, `rahbar:cache:entries:<n>`. Each item is
  the question's embedding (float32, base64) plus the answer payload: answer, citations,
  `answered_from_context`, confidence, retrieved list and provider. Never the request id,
  the history or the summary. The newest `CACHE_MAX_ENTRIES` are kept.
- **Hit:** cosine similarity at or above `CACHE_THRESHOLD` from the ConfigMap, chosen as the
  lowest threshold with zero false hits on the golden questions (docs/PIPELINE.md).
- **Invalidation:** the indexer's last step is `INCR rahbar:cache:generation`
  (indexer/pipeline/invalidate.py). The api reads the generation on every lookup, so the
  next question after a re-index misses. Old lists expire after seven days.
- **Never cached, and never looked up:** follow-ups and questions about an older version
  (entries match on wording alone, so "the 2023 rules" could hit a current answer).
- **Never cached:** abstentions, `answered_from_context: false`, the canned
  fallback, and any answer left without a valid citation.
- **Failure:** every Redis error is a cache miss with a 0.5 s timeout, never a 500. `/readyz`
  still reports Redis as a dependency (§4.3). `CACHE=none` turns the cache off for
  `make dev`, and an unknown value fails at startup.

## Options considered
- **A second Chroma collection.** Chroma does the similarity search natively, and that is
  its real advantage. Rejected because: (1) it is the only collection the api would ever
  write, which breaks the cleanest rule in this system, that the api only reads Chroma
  (CLAUDE.md §1.3, §4.2), and makes `add`/`upsert` legal under `api/`; (2) invalidating
  means deleting and recreating that collection while 3 to 8 pods are writing to it,
  which is the delete-recreate window the indexer avoids (D15); (3) Chroma is a single
  StatefulSet replica already on the hot path of every question, so the cache would add
  load to the one component that cannot scale out.
- **An in-process cache per pod** (functools or a dict). Rejected: each replica would have
  its own cache, so the hit rate drops by the replica count. A re-index could not reach
  the pods to invalidate them, and a restart empties the cache.
- **Redis with a vector index (redis-stack / RediSearch).** Deferred: a different image and
  module for a cache of a few hundred entries. The linear scan costs a few milliseconds
  at 200 entries and is marked with a `ponytail:` comment naming the upgrade path.

## Consequences
- Easier: the api still never writes Chroma; one atomic `INCR` invalidates everything;
  Redis going away only costs speed.
- Harder: similarity is computed in Python over every entry of the current generation,
  so `CACHE_MAX_ENTRIES` bounds the cost and should stay small.
- Watch: `rahbar_cache_lookups_total{result="hit"}` against `{result="miss"}` (the hit
  ratio), and any report of a wrong cached answer. One false hit means the threshold is
  too low, and the fix is to raise it, not to add exceptions.
