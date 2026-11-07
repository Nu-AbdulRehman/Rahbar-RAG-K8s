# ADR 0002: Conversation history lives in the browser

## Status
Accepted · 2026-11-07 (decision D10, D1-P4b)

## Context
§3.2 step 2 skips the cache for follow-up questions, and step 8 stores the turn. A
follow-up ("what about the fee?") cannot be detected or answered without the earlier
turns. The api runs as 3 to 8 replicas behind one Service, so any request can land on
any pod, and a pod can be killed at any time (§4.6). The starter-kit request is
`{"question": ...}` only, so this changes a contract, which STARTER.md says needs an ADR.

## Decision
The browser keeps the conversation and the API stays stateless.

- **Request** gains two optional fields: `history`, a list of `{question, answer}` (at most
  `HISTORY_TURNS` turns from the ConfigMap, default 3; question 1-500 characters, answer
  at most 2,000), and `summary`, one string of at most 1,500 characters covering everything
  older. Anything larger is a 422, like an over-long question.
- **Response** gains `summary` (the updated summary to send back next time) and
  `history_turns` (the window size, so the page does not hard-code it).
- **Window:** when the browser sends a full window of N turns, the API folds the oldest
  one into the summary with one schema-constrained, low-temperature call and returns it.
  The browser then drops that turn. If the summary call fails, the old summary comes back
  unchanged, the failure is counted (`rahbar_summary_failures_total`) and logged, and the
  answer is still returned.
- **Follow-ups:** a question is a follow-up only when history is present and it leans on
  it: a referring word ("it", "that", "they", "there"), an opener like "what about" or
  "and", or four words or fewer. It is retrieved with a standalone query (the previous
  question plus this one). Follow-ups never use the cache, in either direction.
- **History is untrusted.** Anyone can edit localStorage. History goes into the user
  message inside a `<conversation>` block, after the instructions and before the evidence,
  labelled as earlier conversation and not evidence. Citations are still checked against
  this request's retrieved passages only, so a citation copied from history is dropped.
- **Nothing is stored server-side.** "Store the turn" (§3.2 step 8) means one log line
  with the request id and the follow-up flag. History text and the rewritten query are
  logged at DEBUG only.

Requests without `history` behave exactly as before, so the eval harness, CI and the
starter tests are unchanged.

## Options considered
- **Server-side sessions in Redis keyed by a cookie.** Rejected: every replica would read
  and write session state on every question, Redis would become part of the answer path
  (today a Redis outage only costs cache hits), and personal conversation text would
  persist on a PVC that the data-governance ADR would then have to cover.
- **Sticky sessions at the Ingress.** Rejected: a rollout or a deleted pod loses the
  conversation, and HPA scale-down breaks the affinity. That is exactly what §1.3's
  "delete a pod and nothing breaks" rules out.
- **Send the whole transcript every time, no summary.** Rejected: the prompt grows without
  bound, llama3.2:3b's context fills, and the request size cap becomes arbitrary.
- **An LLM rewrite of every follow-up into a standalone question.** Deferred: it adds a
  second model call to every follow-up. Concatenating the previous question gives the
  embedder the missing subject at no cost. Revisit if follow-up recall in the golden set
  is poor.

## Consequences
- Easier: any replica answers any turn; a deleted pod loses nothing; no new state store.
- Harder: the browser can send anything, so every field is size-capped and treated as data.
  The summary is model-written, so a poisoned summary round-trips. It is still only
  context, never instructions and never a citation.
- Watch: `rahbar_followups_total` against request count. A high ratio means the heuristic is
  too eager, and those questions lose the cache. Watch `rahbar_summary_failures_total` too.
