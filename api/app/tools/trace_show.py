"""D2: print the exact context and prompt that produced an answer, from its trace id.

    python -m app.tools.trace_show <trace_id> [--dir DIR] [--json]
    python scripts/trace_show.py <trace_id> --dir traces          (from the repo root)
    kubectl exec -n rahbar deploy/api -- python -m app.tools.trace_show <trace_id>

The prompt is rebuilt, not just echoed: the evidence passages, the question and the
conversation block recorded in the trace go through services/prompt.build_prompt again,
and the SHA-256 of the result is compared with the prompt_hash the api recorded when it
called the model. MATCH means the printed prompt is byte for byte what the model saw.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .traces import load


def find(trace_id: str, directory: str | None, logs: str | None) -> dict[str, Any]:
    found = None
    for record in load(directory, logs):
        if record.get("trace_id") == trace_id:
            found = record                       # the last one wins: ids are unique anyway
    if found is None:
        raise SystemExit(f"trace {trace_id} not found")
    return found


def rebuild(record: dict[str, Any]) -> tuple[str, str, str] | None:
    """(system, user, sha256) rebuilt from the recorded evidence, or None when the query
    never reached the model (abstained, cached, retrieval failed)."""
    if not record.get("evidence"):
        return None
    from ..schemas import Passage
    from ..services.prompt import build_prompt
    from ..services.trace import prompt_hash

    passages = [Passage(**{k: e[k] for k in ("chunk_id", "text", "source", "section",
                                             "page", "score")})
                for e in record["evidence"]]
    temperature = record["generation"]["parameters"]["temperature"]
    prompt = build_prompt(record["query"], passages, temperature, record.get("conversation", ""))
    return prompt.system, prompt.user, prompt_hash(prompt)


def _rule(title: str) -> str:
    return f"\n== {title} " + "=" * max(0, 76 - len(title))


def render(record: dict[str, Any]) -> str:
    emb, gen, ret = record["embedding"], record["generation"], record["retrieval"]
    out = [f"trace {record['trace_id']}  {record['timestamp']}  pod {record.get('pod')}",
           f"query:            {record['query']}",
           f"rewritten query:  {record.get('rewritten_query')}",
           f"collection:       {record['collection']}",
           f"embedding:        {emb['model']} version {emb.get('version')} "
           f"dimension {emb.get('dimension')}",
           f"llm:              {gen['provider']} {gen['model']} {json.dumps(gen['parameters'])}",
           f"outcome:          {record['outcome']}   cache {record['cache']['lookup']}"
           f" (stored {record['cache'].get('stored')})",
           f"filters:          {json.dumps(ret.get('filters'))}",
           f"reranker:         {ret.get('reranker')}; prompt order {ret.get('reranked_order')}"]
    flagged = {g.get("chunk_id") for g in record.get("guardrails", []) if g.get("chunk_id")}
    out.append(_rule("retrieved chunks"))
    out.append(f"{'#':>2} {'score':>6} {'floor':5} {'chunk_id':34} {'doc_id @ version':40} "
               "superseded rail")
    for c in ret.get("chunks", []):
        doc = f"{c.get('doc_id')} @ {c.get('doc_version')}"
        out.append(f"{c['rank']:>2} {c['score']:>6.3f} {'ok' if c.get('above_floor') else 'below':5} "
                   f"{c['chunk_id'][:34]:34} {doc[:40]:40} {str(c.get('superseded')):10} "
                   f"{'FLAGGED' if c['chunk_id'] in flagged else ''}")
    out.append(_rule("guardrails"))
    out += [f"- {json.dumps(g)}" for g in record.get("guardrails", [])] or ["- none acted"]
    out.append(_rule("latency (ms)"))
    out.append(json.dumps(record.get("latency_ms", {})))

    rebuilt = rebuild(record)
    if rebuilt is None:
        out.append(_rule("prompt"))
        out.append(f"no prompt: this query never reached the model (outcome "
                   f"{record['outcome']}). The chunks above are the whole context.")
    else:
        system, user, digest = rebuilt
        recorded = gen.get("prompt_hash")
        verdict = "MATCH" if digest == recorded else "MISMATCH (prompt.py changed since?)"
        out.append(_rule("prompt rebuilt from the trace"))
        out.append(f"recorded prompt_hash {recorded}")
        out.append(f"rebuilt  prompt_hash {digest}  {verdict}")
        out.append(_rule("system message"))
        out.append(system)
        out.append(_rule("user message (conversation, numbered evidence, question)"))
        out.append(user)
    out.append(_rule("response"))
    resp = record.get("response") or {}
    out.append(resp.get("answer", ""))
    out.append(f"answered_from_context {resp.get('answered_from_context')}  "
               f"confidence {resp.get('confidence')}  citations "
               f"{json.dumps(resp.get('citations'))}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trace_show", description=__doc__.splitlines()[0])
    parser.add_argument("trace_id")
    parser.add_argument("--dir", help="trace directory (default: TRACE_DIR, else ./traces)")
    parser.add_argument("--logs", help="read `kubectl logs` output from this file, or - "
                                       "(stdout copies carry no prompt to rebuild)")
    parser.add_argument("--json", action="store_true", help="print the raw record")
    args = parser.parse_args(argv)
    record = find(args.trace_id, args.dir, args.logs)
    print(json.dumps(record, indent=2, ensure_ascii=False) if args.json else render(record))
    return 0


if __name__ == "__main__":
    sys.exit(main())
