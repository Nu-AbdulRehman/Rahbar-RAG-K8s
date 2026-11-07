# ADR 0004: LLM provider, and what data goes where

## Status
Accepted · 2026-11-07

## Context
Every answer needs one generation call, and every question and every indexed chunk needs
an embedding. Where those calls go decides what leaves the machine. The corpus is public
(nine FAST-NUCES documents, docs/CORPUS.md), but the questions, and the conversation the
browser sends with them (ADR 0002), are user text: a student may type their roll number,
their CGPA or a disciplinary case into the box. The brief (§3.5) asks for a provider that
can be swapped without touching the rest of the code, and for the embedding route to be
stated.

## Decision
- **Generation:** `LLM_PROVIDER=ollama-host`, llama3.2:3b through Ollama on the host
  machine, reached from the cluster at `host.minikube.internal:11434` (decision D1,
  k8s/base/configmap.yaml). Nothing leaves the laptop.
- **Embeddings:** nomic-embed-text through the same Ollama host, for both the indexer and
  the api. `EMBED_MODEL` is one ConfigMap key read by both, and the api refuses readiness
  if the index was built with another model or dimension (api/app/services/pin.py).
- **The swap:** `LLM_PROVIDER=hosted` is one file (api/app/providers/llm/hosted.py) and
  one ConfigMap value plus `HOSTED_BASE_URL`. The key comes only from the `rahbar-secret`
  Secret, created with `make secret`, never a committed file.

What each part of the system sees and keeps:

| Data | Sent to the model | Stored | Logged at INFO |
| --- | --- | --- | --- |
| System instructions | yes | in the image | no |
| Retrieved passages (at most TOP_K=5, public text) | yes, delimited as evidence | Chroma PVC | chunk ids and scores only |
| The question | yes | the Redis cache keeps its **embedding**, not its text, for safe standalone answers only | no |
| Conversation (summary + last HISTORY_TURNS turns) | yes, as context, never as evidence | the user's browser (localStorage) only | no |
| The answer | it is the model's output | Redis, for safe answers, until the next re-index or 7 days | no |
| The LLM key | no | the Secret only | never (excluded from the Settings repr) |

The prompt, the history and the rewritten query are logged at DEBUG only
(api/app/services/answer.py), and the ConfigMap pins `LOG_LEVEL=INFO`. Request ids,
chunk ids, scores and flags are logged; question text is not.

## Options considered
- **Hosted model as the default** (an OpenAI-compatible endpoint). Faster and stronger
  answers, but every question and the browser's conversation would go to a third party,
  and the deployment would depend on a key and a network path to the internet. Kept as
  the swap, not the default.
- **Ollama inside the cluster** (`ollama-incluster`). Keeps data in the cluster too, but
  a 3B model needs about 3 GB of memory and the GPU is on the host; a 5 GB minikube cannot
  hold it next to Chroma and three api pods. Deferred bonus (decision Q6).
- **A separate embedding service.** A second model server to pin and keep in step with
  the indexer. Using the same Ollama host for both means one place where the model name
  lives.

## Consequences
- With `ollama-host`, no user text leaves the machine, and the NetworkPolicy allows the
  api and the indexer to reach only the Ollama host's address
  (k8s/base/networkpolicy.yaml), not the internet.
- Switching to `hosted` is a data-sharing decision, not only a config change: the
  question and the conversation go to the provider in `HOSTED_BASE_URL`, under its
  retention terms. Anyone making that switch must also open the NetworkPolicy to that
  endpoint and should tell users.
- Model output is untrusted. It is schema-validated, its citations are checked against
  what was retrieved, and it is never executed or used to build a query, a shell command
  or a path (api/app/services/generation.py).
- The host's Ollama is a single point of failure for both indexing and answering. When
  it is down, the api returns the canned answer (never a 5xx) and the indexer Job fails
  and retries.
