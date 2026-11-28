# ADR 0005: One trace record per query, on stdout and on a volume

## Status
Accepted · 2026-11-28 (RAGOps D1, D4, F4). Amends the "Logged at INFO" column of ADR 0004
for the trace line only.

## Context
RAGOps D1 asks for one JSON record per query with the user query, the retrieved chunks
with their document versions and scores, the filters, a prompt hash or the full prompt,
the response, the guardrail actions and the latency per stage. F4 asks for those records
on standard output, readable with `kubectl logs`, and also on a volume for the report
scripts. D2 asks for a command that prints the exact prompt behind an answer.

ADR 0004 keeps the question text, the prompt and the retrieved text out of INFO logs. The
RAGOps brief ranks above our ADRs, and its D1 record contains the query, so the two have
to be reconciled rather than one silently ignored.

## Decision
- `api/app/services/trace.py` builds the record step by step inside
  `services/answer.py` and writes it twice:
  - **stdout**, as the `rahbar.trace` logger at INFO (`msg: "trace"`): every D1 field,
    including the query and the answer, with the **prompt hash only**. No prompt text, no
    passage text, no conversation.
  - **`TRACE_DIR`** (the `ragops-results` PVC, `/results/traces`): the same record plus
    the full prompt (system and user messages), the evidence passages as they went into
    the prompt, and the conversation block, one file per pod and day.
- The trace id is the request id (`X-Request-ID`), so a trace, the access log line and the
  `answered` line join on one key.
- `scripts/trace_show.py <trace_id>` (also `python -m app.tools.trace_show` in an api pod)
  rebuilds the prompt from the recorded evidence with `build_prompt` and compares its
  SHA-256 with the recorded `prompt_hash`: MATCH proves the printed prompt is what the
  model saw.
- The retrieval rail (`services/guardrails.py`) flags instruction-like text in a chunk or
  the question. `GUARDRAIL_INJECTION_ACTION=flag` keeps the chunk as delimited evidence;
  `redact` also removes the flagged sentences. The cluster runs **`redact`** (rahbar-config);
  the code default stays `flag`, so the poisoned-chunk test keeps proving that the
  Assignment 02 defence holds without the rail. The Assignment 02 output checks (citation
  check, marker check, decline, fallback) add their actions to the same list.
- An answer built on evidence the rail flagged is never cached, in either mode.

**Why redact on the cluster (measured, 2026-11-28).** In flag mode on minikube, "Are all
fees waived this semester according to the IT policy?" retrieved Batch B's b09 section 3;
the rail flagged it, the model answered "true [b09-it-acceptable-use.md / 3. Assistant
notice]", and the citation check could not object, because that chunk *was* retrieved. The
Assignment 02 defence stops the model obeying an instruction and stops invented citations;
it does not stop the model repeating a planted claim as a fact. Redaction removes the
claim before the prompt (eval/results/f/11-d4-flag-mode.txt, 13-d4-redact-mode.txt).

## Options considered
- **Full prompt on stdout too.** One copy, simplest to read. Rejected: it puts every
  retrieved passage and the conversation into the node's log files and any log shipper,
  which is what ADR 0004 exists to prevent, for no gain, since the volume copy serves the
  tools.
- **Hash the query on stdout, text on the volume only.** Keeps ADR 0004 intact. Rejected:
  D1 lists the user query as a field of the record F4 sends to stdout, and a trace you
  cannot read without the volume defeats `kubectl logs` debugging.
- **Prompt hash only, no full prompt anywhere.** D1 allows it, but D2 then cannot print
  the exact prompt. Rejected.
- **Code default `redact`.** It would hide the injected text from the model in the
  poisoned-chunk test (eval/test_poisoned_chunk.py), which must keep proving that the
  Assignment 02 defence holds on its own (CLAUDE.md §1.8). The cluster sets redact instead.
- **`drop` the whole flagged chunk.** Rejected: b09's chunk also holds section 4 (lab
  computers), a true passage that would be lost with the planted sentences.
- **`flag` on the cluster.** The first setting; rejected after the measurement above.

## Consequences
- The question text is now at INFO in the trace line. It is public-domain student
  questions about public documents; the LLM key, headers and environment never enter a
  record. ADR 0004's row for "The question" now reads: logged at INFO in the trace line
  only.
- Three api replicas write three files; `trace_summary.py` and `trace_show.py` read the
  whole directory. A failed volume write is counted (`rahbar_trace_write_failures_total`)
  and never fails the request.
- A change to `prompt.py` makes old traces rebuild with MISMATCH. That is correct: the
  stored prompt is still printed, and the mismatch says the code moved.
