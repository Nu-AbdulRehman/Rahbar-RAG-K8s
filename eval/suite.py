"""The RAGOps offline test suite (Part B): three levels, one command, one result file.

    python eval/suite.py --api http://localhost:8000 [--collection rahbar] [--runs 2]

    module      embedding: paraphrase vs unrelated cosine and the gap, time per chunk,
                determinism (embed the same text twice, largest difference)
    component   retrieval: recall@3, recall@5, MRR, nDCG@5 on the golden set, then the
                same with typos in the queries (the noise test)
    end-to-end  answers through the api: faithfulness (llama3.2:3b as the judge),
                abstention on unanswerable questions, citation validity, latency p50/p95

Retrieval runs the api's own code (ChromaRetriever, the follow-up rewrite, the
old-version router), so the component level measures what production does, on whichever
collection --collection names. Chroma and Ollama come from the api's environment
variables (CHROMA_HOST, CHROMA_PORT, OLLAMA_URL, EMBED_MODEL, TOP_K, LLM_MODEL).

--runs 2 runs everything twice with the same seeds and reports the difference per metric
(stochasticity). The result goes to eval/results/<timestamp>-<label>.json with a summary
table, and eight answered questions are written beside it for hand-labelling the judge:

    python eval/suite.py agreement eval/results/<file>-faithfulness-sample.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "api"))
sys.path.insert(0, str(HERE))

from ragops_metrics import (  # noqa: E402
    add_typos,
    cosine,
    diff,
    max_abs_diff,
    mean,
    ndcg_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
)
from run_eval import _valid_citations, expect_found  # noqa: E402

SEED = 42
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"supported": {"type": "boolean"}, "unsupported": {"type": "string"}},
    "required": ["supported", "unsupported"],
}
JUDGE_SYSTEM = (
    "You check whether an answer is supported by the context. Reply with JSON only. "
    "supported is true when every factual claim in the answer is stated in, or follows "
    "directly from, the context; false when any claim is missing from or contradicts it. "
    "unsupported names the first unsupported claim, or is empty.")


def load_golden(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _settings(collection: str | None) -> Any:
    from dataclasses import replace

    from app.config import get_settings

    settings = get_settings()
    return replace(settings, collection=collection) if collection else settings


def _embedder(settings: Any) -> Any:
    from app.providers.llm.embed import OllamaEmbedder

    return OllamaEmbedder(settings)


# --- module level -------------------------------------------------------------------------
def module_level(settings: Any, pairs_path: Path, sample_texts: list[str]) -> dict:
    pairs = [json.loads(line) for line in pairs_path.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    sims: dict[str, list[float]] = {"paraphrase": [], "unrelated": []}
    for pair in pairs:
        sims[pair["kind"]].append(cosine(_embedder(settings).embed(pair["a"]),
                                         _embedder(settings).embed(pair["b"])))
    times = []
    for text in sample_texts:
        started = time.perf_counter()
        _embedder(settings).embed(text)
        times.append((time.perf_counter() - started) * 1000)
    probe = sample_texts[0] if sample_texts else "Students must attend every lecture."
    first, second = _embedder(settings).embed(probe), _embedder(settings).embed(probe)
    para, unrel = mean(sims["paraphrase"]), mean(sims["unrelated"])
    return {
        "embed_model": settings.embed_model,
        "paraphrase_pairs": len(sims["paraphrase"]), "unrelated_pairs": len(sims["unrelated"]),
        "paraphrase_mean_cosine": para, "unrelated_mean_cosine": unrel,
        "gap": round(para - unrel, 4) if para is not None and unrel is not None else None,
        "embed_ms_per_chunk_mean": round(sum(times) / len(times), 2) if times else None,
        "embed_ms_per_chunk_p95": round(percentile(times, 95) or 0, 2) if times else None,
        "chunks_timed": len(times),
        "determinism_max_abs_diff": max_abs_diff(first, second),
        "dimension": len(first),
    }


# --- component level ----------------------------------------------------------------------
def _retrieve(retriever: Any, settings: Any, question: str, history: list[dict]) -> list[dict]:
    from app.schemas import Turn
    from app.services.conversation import is_follow_up, retrieval_query
    from app.services.query import asks_about_older_version

    turns = [Turn(**t) for t in history]
    query = retrieval_query(question, turns) if turns and is_follow_up(question, turns) \
        else question
    passages = retriever.retrieve(query, k=settings.top_k,
                                  include_superseded=asks_about_older_version(query))
    return [{"chunk_id": p.chunk_id, "source": p.source, "section": p.section,
             "page": p.page, "score": p.score} for p in passages]


def _score_retrieval(golden: list[dict], retrieved: dict[str, list[dict]]) -> dict:
    per: dict[str, dict[str, list]] = {}
    rows = []
    for q in golden:
        if not q["relevant"]:
            continue
        got = retrieved[q["id"]]
        row = {"recall@3": recall_at_k(q["relevant"], got, 3),
               "recall@5": recall_at_k(q["relevant"], got, 5),
               "mrr": reciprocal_rank(q["relevant"], got),
               "ndcg@5": ndcg_at_k(q["relevant"], got, 5)}
        rows.append(row)
        for name, value in row.items():
            per.setdefault(q["type"], {}).setdefault(name, []).append(value)
    overall = {name: mean([r[name] for r in rows]) for name in ("recall@3", "recall@5",
                                                                "mrr", "ndcg@5")}
    return {**overall, "questions": len(rows),
            "by_type": {t: {n: mean(v) for n, v in m.items()} | {"questions": len(m["mrr"])}
                        for t, m in sorted(per.items())}}


def component_level(settings: Any, golden: list[dict]) -> tuple[dict, dict[str, list[dict]]]:
    from app.retrieval.chroma import ChromaRetriever

    retriever = ChromaRetriever(settings, _embedder(settings))
    clean = {q["id"]: _retrieve(retriever, settings, q["question"], q.get("history", []))
             for q in golden}
    rng = random.Random(SEED)
    noisy = {q["id"]: _retrieve(retriever, settings, add_typos(q["question"], rng),
                                q.get("history", [])) for q in golden}
    base, typo = _score_retrieval(golden, clean), _score_retrieval(golden, noisy)
    change = {name: round((typo[name] or 0) - (base[name] or 0), 4)
              for name in ("recall@3", "recall@5", "mrr", "ndcg@5")}
    top1 = [got[0]["score"] for got in clean.values() if got]
    return {**base, "top1_similarity_mean": mean(top1),
            "noise_test": {"kind": "typos in about 15 % of query words, seed 42",
                           **{k: typo[k] for k in ("recall@3", "recall@5", "mrr", "ndcg@5")},
                           "change": change}}, clean


# --- end-to-end level ---------------------------------------------------------------------
def _ask(client: httpx.Client, api: str, host: str | None, q: dict) -> tuple[dict, float]:
    body: dict[str, Any] = {"question": q["question"]}
    if q.get("history"):
        body["history"] = q["history"]
    headers = {"Host": host} if host else {}
    started = time.perf_counter()
    response = client.post(f"{api.rstrip('/')}/api/ask", json=body, headers=headers)
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    return response.json(), elapsed


def _context(settings: Any, chunk_ids: list[str]) -> str:
    from app.retrieval.chroma import ChromaRetriever

    if not chunk_ids:
        return ""
    collection = ChromaRetriever(settings, _embedder(settings)).collection()
    got = collection.get(ids=chunk_ids, include=["documents"])
    by_id = dict(zip(got["ids"], got["documents"]))
    return "\n\n".join(f"[{i + 1}] {by_id.get(c, '')}" for i, c in enumerate(chunk_ids))


def judge(settings: Any, client: httpx.Client, question: str, answer: str,
          context: str) -> dict:
    """Faithfulness: is every claim in the answer supported by the retrieved context?
    llama3.2:3b on host Ollama (decision R11), temperature 0, fixed seed."""
    response = client.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json={
        "model": settings.llm_model, "stream": False, "format": JUDGE_SCHEMA,
        "options": {"temperature": 0, "seed": SEED},
        "messages": [{"role": "system", "content": JUDGE_SYSTEM},
                     {"role": "user", "content": f"<context>\n{context}\n</context>\n\n"
                                                 f"<question>{question}</question>\n\n"
                                                 f"<answer>{answer}</answer>"}]})
    response.raise_for_status()
    try:
        verdict = json.loads(response.json()["message"]["content"])
        return {"supported": bool(verdict["supported"]),
                "unsupported": str(verdict.get("unsupported", ""))}
    except (KeyError, ValueError, TypeError):
        return {"supported": None, "unsupported": "judge returned invalid JSON"}


def end_to_end(settings: Any, golden: list[dict], api: str, host: str | None) -> tuple[dict, list]:
    answers = []
    with httpx.Client(timeout=120) as client:
        for q in golden:
            response, seconds = _ask(client, api, host, q)
            row: dict[str, Any] = {"id": q["id"], "type": q["type"], "question": q["question"],
                                   "answer": response.get("answer", ""),
                                   "answered_from_context": response.get("answered_from_context"),
                                   "citations": response.get("citations") or [],
                                   "retrieved": response.get("retrieved") or [],
                                   "latency_s": round(seconds, 3),
                                   "correct": expect_found(q.get("expect"), response)}
            valid, total = _valid_citations(response)
            row["citations_valid"], row["citations_total"] = valid, total
            if row["answered_from_context"]:
                ids = [r["chunk_id"] for r in row["retrieved"]]
                row["context"] = _context(settings, ids)
                row["judge"] = judge(settings, client, q["question"], row["answer"],
                                     row["context"])
            answers.append(row)
    unanswerable = [a for a in answers if a["type"] == "unanswerable"]
    judged = [a["judge"]["supported"] for a in answers if a.get("judge")]
    latencies = [a["latency_s"] for a in answers]
    valid = sum(a["citations_valid"] for a in answers)
    total = sum(a["citations_total"] for a in answers)
    return {
        "faithfulness": round(sum(1 for j in judged if j) / len(judged), 4) if judged else None,
        "faithfulness_judged": len(judged),
        "abstention_correctness": round(sum(1 for a in unanswerable
                                            if a["answered_from_context"] is False)
                                        / len(unanswerable), 4) if unanswerable else None,
        "unanswerable": len(unanswerable),
        "citation_validity": round(valid / total, 4) if total else None,
        "citations": total,
        "answer_correctness": mean([a["correct"] for a in answers]),
        "latency_p50_s": round(percentile(latencies, 50) or 0, 3),
        "latency_p95_s": round(percentile(latencies, 95) or 0, 3),
        "answered": sum(1 for a in answers if a["answered_from_context"]),
        "questions": len(answers),
    }, answers


# --- the suite ----------------------------------------------------------------------------
def _sample_texts(settings: Any, n: int = 32) -> list[str]:
    from app.retrieval.chroma import ChromaRetriever

    got = ChromaRetriever(settings, _embedder(settings)).collection().get(
        limit=n, include=["documents"])
    return [d for d in got["documents"] if d]


def run_once(args: argparse.Namespace, settings: Any, golden: list[dict]) -> tuple[dict, list]:
    random.seed(SEED)
    module = module_level(settings, args.pairs, _sample_texts(settings))
    component, _ = component_level(settings, golden)
    e2e, answers = end_to_end(settings, golden, args.api, args.host)
    return {"module": module, "component": component, "end_to_end": e2e}, answers


def summary_table(result: dict) -> str:
    m, c, e = result["module"], result["component"], result["end_to_end"]

    def f(v: Any) -> str:
        return "-" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v)

    rows = [
        ("module", "paraphrase mean cosine", m["paraphrase_mean_cosine"]),
        ("module", "unrelated mean cosine", m["unrelated_mean_cosine"]),
        ("module", "gap", m["gap"]),
        ("module", "embed ms per chunk (mean)", m["embed_ms_per_chunk_mean"]),
        ("module", "determinism max |diff|", m["determinism_max_abs_diff"]),
        ("component", "recall@3", c["recall@3"]), ("component", "recall@5", c["recall@5"]),
        ("component", "MRR", c["mrr"]), ("component", "nDCG@5", c["ndcg@5"]),
        ("component", "recall@5 with typos", c["noise_test"]["recall@5"]),
        ("component", "MRR with typos", c["noise_test"]["mrr"]),
        ("end-to-end", "faithfulness", e["faithfulness"]),
        ("end-to-end", "abstention correctness", e["abstention_correctness"]),
        ("end-to-end", "citation validity", e["citation_validity"]),
        ("end-to-end", "latency p50 (s)", e["latency_p50_s"]),
        ("end-to-end", "latency p95 (s)", e["latency_p95_s"]),
    ]
    out = ["| level | metric | value |", "| --- | --- | --- |"]
    out += [f"| {level} | {name} | {f(value)} |" for level, name, value in rows]
    return "\n".join(out)


def write_sample(path: Path, answers: list[dict], n: int = 8) -> None:
    """Eight answered questions with the judge's verdict and an empty human label."""
    rows = [a for a in answers if a.get("judge")][:n]
    with path.open("w", encoding="utf-8") as f:
        for a in rows:
            f.write(json.dumps({"id": a["id"], "question": a["question"], "answer": a["answer"],
                                "context": a["context"],
                                "judge_supported": a["judge"]["supported"],
                                "human_supported": None, "labelled_by": None},
                               ensure_ascii=False) + "\n")


def agreement(path: Path) -> int:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    labelled = [r for r in rows if r.get("human_supported") is not None]
    if not labelled:
        print(f"no hand labels yet in {path}: set human_supported to true or false")
        return 1
    agree = sum(r["human_supported"] == r["judge_supported"] for r in labelled)
    print(f"judge agrees with the hand labels on {agree} of {len(labelled)} "
          f"({agree / len(labelled):.0%})")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "agreement":
        return agreement(Path(argv[1]))
    parser = argparse.ArgumentParser(description="Run the RAGOps Part B suite.")
    parser.add_argument("--api", required=True, help="the api's base URL")
    parser.add_argument("--host", help="Host header, when going through the Ingress")
    parser.add_argument("--collection", help="Chroma collection (default: CHROMA_COLLECTION)")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.jsonl")
    parser.add_argument("--pairs", type=Path, default=HERE / "embedding_pairs.jsonl")
    parser.add_argument("--runs", type=int, default=1, help="2 for the stochasticity check")
    parser.add_argument("--label", default="run", help="e.g. baseline, c200, minilm")
    parser.add_argument("--out-dir", type=Path, default=HERE / "results")
    args = parser.parse_args(argv)

    settings = _settings(args.collection)
    golden = load_golden(args.golden)
    runs, answers = [], []
    for i in range(args.runs):
        result, run_answers = run_once(args, settings, golden)
        runs.append(result)
        answers.append(run_answers)
        print(f"run {i + 1} of {args.runs} done", flush=True)

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{stamp}-{args.label}.json"
    body = {"label": args.label, "timestamp": stamp, "collection": settings.collection,
            "embed_model": settings.embed_model, "llm_model": settings.llm_model,
            "top_k": settings.top_k, "golden": args.golden.name, "seed": SEED,
            "questions": len(golden), **runs[0],
            "summary_table": summary_table(runs[0]),
            "answers": answers[0]}
    if len(runs) > 1:
        body["stochasticity"] = {"runs": len(runs), "second_run": runs[1],
                                 "difference": diff(runs[0], runs[1])}
    out.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    write_sample(out.with_name(out.stem + "-faithfulness-sample.jsonl"), answers[0])
    print(body["summary_table"])
    if len(runs) > 1:
        changed = {k: v for k, v in body["stochasticity"]["difference"].items() if v}
        print("\nstochasticity (run 2 - run 1), non-zero only:", json.dumps(changed, indent=1))
    print(f"\nresults written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
