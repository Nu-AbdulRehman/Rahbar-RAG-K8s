"""Build the RAGOps report PDF (Part G): docs/report/RAGOps-Report.pdf.

    uv run --with reportlab==4.2.5 python docs/report/build_report.py

Letter (8.5 x 11 in), 1 in margins, Times New Roman, black and white, every table cell
outlined. The text is the report; the numbers come from the committed result files that
each section names. The appendix embeds docs/report/screenshots/*.png uncropped.
"""

from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "screenshots"
OUT = HERE / "RAGOps-Report.pdf"
# Times New Roman's four TTFs: Windows has them; on Linux install ttf-mscorefonts-installer
# (/usr/share/fonts/truetype/msttcorefonts) or set TNR_FONTS to a folder holding them.
FONTS = Path(os.environ.get("TNR_FONTS") or next(
    (d for d in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/msttcorefonts",
                 "/Library/Fonts/Microsoft") if Path(d, "times.ttf").exists()),
    "C:/Windows/Fonts"))

for name, file in (("TNR", "times.ttf"), ("TNR-B", "timesbd.ttf"),
                   ("TNR-I", "timesi.ttf"), ("TNR-BI", "timesbi.ttf")):
    pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-B", italic="TNR-I",
                              boldItalic="TNR-BI")

BODY = ParagraphStyle("body", fontName="TNR", fontSize=11, leading=13.4, spaceAfter=5)
CELL = ParagraphStyle("cell", fontName="TNR", fontSize=9.5, leading=11.2)
HEAD = ParagraphStyle("head", parent=CELL, fontName="TNR-B")
H1 = ParagraphStyle("h1", fontName="TNR-B", fontSize=13, leading=16, spaceBefore=9,
                    spaceAfter=4, keepWithNext=1)
H2 = ParagraphStyle("h2", fontName="TNR-B", fontSize=11, leading=13.4, spaceBefore=5,
                    spaceAfter=3, keepWithNext=1)
TITLE = ParagraphStyle("title", fontName="TNR-B", fontSize=16, leading=20,
                       alignment=TA_CENTER, spaceAfter=4)
CENTER = ParagraphStyle("center", parent=BODY, alignment=TA_CENTER, spaceAfter=2)
CAPTION = ParagraphStyle("caption", parent=BODY, fontSize=10, leading=12, spaceAfter=3)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=12, bulletIndent=2, spaceAfter=3)

WIDTH = LETTER[0] - 2 * inch


def p(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(text, style)


def bullets(*items: str) -> list[Paragraph]:
    return [Paragraph(t, BULLET, bulletText="\u2022") for t in items]


def table(rows: list[list[str]], widths: list[float]) -> Table:
    """Every cell outlined, header row bold, no shading."""
    scale = WIDTH / sum(widths)
    data = [[Paragraph(c, HEAD if i == 0 else CELL) for c in row] for i, row in enumerate(rows)]
    t = Table(data, colWidths=[w * scale for w in widths], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


def caption(text: str) -> Paragraph:
    return p(f"<b>{text}</b>", CAPTION)


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("TNR", 9.5)
    canvas.drawCentredString(LETTER[0] / 2, 0.6 * inch, str(doc.page))
    canvas.restoreState()


S: list = []

# --- Page 1 -------------------------------------------------------------------------
S += [
    p("RAGOps for RAHBAR: Verify, Test, Gate, Trace and Run on Kubernetes", TITLE),
    p("Assignment 03 report", CENTER),
    Spacer(1, 4),
    table([["Member", "Name", "Roll number", "GitHub account"],
           ["Member 1", "M. Abdul Rehman", "24I-3001", "Nu-AbdulRehman"],
           ["Member 2", "M. Tahir Habib", "24I-3087", "MTH99910"]], [1, 1.6, 1.1, 1.4]),
    Spacer(1, 5),
    p("Repository: https://github.com/Nu-AbdulRehman/Rahbar-RAG-K8s. Every number in this "
      "report comes from a committed file named beside it (eval/results/, traces/, "
      "docs/failure-log.md). <i>Cluster</i> numbers are Kubernetes Jobs on minikube; "
      "<i>local</i> numbers are the same code on a laptop stack (Chroma in Docker, Ollama on "
      "the host GPU). The golden set has 44 questions: 18 answerable, 12 unanswerable, 14 hard; "
      "8 written by hand, 8 synthetic ones reviewed by both members."),
]

S += [p("1. Pipeline stages (paper Figure 3)", H1),
      table([
          ["Stage", "What our pipeline does", "File", "What is missing"],
          ["Ingest", "Downloads the corpus listed in sources.yaml into the data lake, checks each "
           "file's SHA-256 against MANIFEST.md, extracts text (OCR for scanned pages).",
           "corpus/fetch.py, indexer/pipeline/extract.py", "Archived versions are downloaded "
           "again on every run (R17, WONTFIX)."],
          ["Verify", "Quality, completeness, recency and uniqueness per document, with a reason; "
           "a failure moves it to quarantine/; one report per run.",
           "indexer/pipeline/verify.py", "No check reads intent: an injected instruction "
           "passes (Q4 a)."],
          ["Update data lake", "Intake from incoming/, archive of superseded versions, restore "
           "(rollback), one run at a time (lake lock).", "indexer/pipeline/lake.py, ops.py",
           "Catalog is rewritten in place (single writer)."],
          ["Update retrieval sources", "Content-hash sync: only new or changed chunks are "
           "embedded, flag changes are metadata updates, stale ids are deleted.",
           "indexer/pipeline/store.py", "No re-embedding schedule when the model is re-pulled."],
          ["Offline testing", "Three-level suite on the golden set, then the release gate; both "
           "as one Job.", "eval/suite.py, scripts/gate.py, k8s/eval-job.yaml",
           "Faithfulness judge is a 3B model (75 % agreement)."],
          ["Live testing", "One trace per query (stdout and volume), metrics on /metrics, a "
           "summary over a time window, the retrieval rail.",
           "api/app/services/trace.py, guardrails.py, app/tools/", "No user feedback signal; "
           "no shadow traffic to the candidate."],
          ["Check coverage", "Nearest golden question per live query; exits 1 under 85 % at "
           "cosine 0.65.", "eval/query_coverage.py, k8s/coverage-job.yaml",
           "The live log is written by us, not real users."],
      ], [1.05, 2.6, 1.6, 1.6])]

S += [p("2. The five qualities (paper Table 2)", H1),
      table([
          ["Quality", "What we measure", "Threshold", "Evidence"],
          ["Adaptability", "A pipeline change (top_k, chunking, embedding model) measured "
           "against the baseline at three levels; thresholds changed without a rebuild.",
           "Gate: recall@5 drop at most 0.02, faithfulness at least 0.64, p95 at most 25 s, "
           "abstention not below baseline.", "eval/results/cluster-m1/04, 05; "
           "eval/results/f/03-gate-configmap-edit.txt"],
          ["Monitorability", "Top-1 similarity distribution, abstention rate, cache hit rate, "
           "p95 per stage, injection flags.", "Coverage at least 85 %; abstention correctness "
           "1.00.", "eval/results/f/08, 15-trace-summary-all.txt"],
          ["Observability", "Every query's chunks, scores, filters, prompt, model and "
           "parameters, guardrail actions and stage latencies.", "Every query has a trace; the "
           "rebuilt prompt hash must MATCH.", "eval/results/f/05, 06-trace-show.txt"],
          ["Traceability", "doc_id, doc_version, superseded and content hash per chunk; "
           "collection; embedding model digest.", "After a rollout undo, a new trace shows the "
           "previous collection and model.", "eval/results/f/14-release-rollout.txt"],
          ["Reliability", "Unchanged-corpus re-runs, rolling release, rollback, readiness on the "
           "embedding pin, measured resources.", "0 chunks embedded on an unchanged corpus; 3 "
           "ready api pods during a release (maxUnavailable 0).",
           "eval/results/cluster-m1/02, f/14, f5/resources.md"],
      ], [1.0, 2.35, 1.95, 1.55])]

# --- Part A --------------------------------------------------------------------------
S += [p("3. Results", H1), p("Part A. Data management", H2),
      p("Verification runs after extraction and before chunking. A quality, completeness or "
        "uniqueness failure quarantines the document with a reason file; a recency failure "
        "archives the older version, which stays indexed with <i>superseded: true</i>. Batch B "
        "(12 documents) through the cluster ingestion Job (eval/results/f/09):"),
      table([
          ["File", "Planted problem", "Failed check", "Action"],
          ["b02, b04", "exact duplicates of b01, b03", "uniqueness (same SHA-256)", "quarantine"],
          ["b05", "near duplicate of b03", "uniqueness (cosine 0.9997, threshold 0.98)",
           "quarantine"],
          ["b06", "truncated PDF", "quality (PdfminerException), completeness", "quarantine"],
          ["b07", "missing title and version", "completeness", "quarantine"],
          ["b11", "scan with almost no text", "quality, completeness", "quarantine"],
          ["b08", "newer version of the fee page", "recency, on the 2026-27 page",
           "b08 indexed, old page archived"],
          ["b09", "injected instruction", "none (by design)", "indexed; redacted at query time"],
          ["b01, b03, b10, b12", "none", "none", "indexed"],
      ], [1.2, 1.9, 2.2, 1.6]),
      Spacer(1, 5),
      table([
          ["Incremental run", "Embedded", "Metadata only", "Unchanged", "Deleted", "Evidence"],
          ["First ingestion (cluster)", "803", "0", "0", "0", "f/01"],
          ["Unchanged corpus (cluster)", "<b>0</b>", "0", "803", "0", "cluster-m1/02, f/02"],
          ["Batch B (cluster)", "21", "10", "793", "0", "f/09"],
          ["One changed document", "1", "0", "836", "0", "a/05"],
          ["One deleted document", "0", "0", "834", "3", "a/06: 0 chunks left for its doc_id"],
          ["Rollback to the 2026-27 fee page", "0", "10", "824", "0", "a/07"],
          ["Roll forward to 2027-28", "0", "13", "821", "0", "a/08"],
          ["Two runs started together (cluster)", "0 and 0", "0", "803", "0",
           "cluster-m1/09: the second waits"],
      ], [2.1, 0.8, 0.9, 0.85, 0.7, 1.9]),
      p("Rollback is <i>python -m pipeline.ops restore fee-structure-page 2026-27</i>; the next "
        "run flips the metadata without re-embedding. Two bugs found by real runs were fixed "
        "with tests: a restored version was re-archived by the next run's recency check, and "
        "two overlapping ingestion runs corrupted catalog.json (now a lake lock).",
        ParagraphStyle("bodytop", parent=BODY, spaceBefore=5))]

# --- Part B --------------------------------------------------------------------------
S += [p("Part B. Offline testing at three levels", H2),
      p("One command, <i>python eval/suite.py</i> (on the cluster <i>kubectl apply -f "
        "k8s/eval-job.yaml</i>), writes a timestamped result file with the summary table."),
      table([
          ["Level", "Metric", "Cluster baseline", "Local baseline"],
          ["Module", "Paraphrase / unrelated mean cosine (16 + 16 pairs); gap",
           "0.760 / 0.368; 0.392", "0.760 / 0.367; 0.392"],
          ["Module", "Embedding time per chunk, mean; determinism (largest difference)",
           "74.8 ms; 0.0", "57.2 ms; 0.0"],
          ["Component", "recall@3 / recall@5 / MRR / nDCG@5", "0.500 / 0.562 / 0.465 / 0.490",
           "0.625 / 0.688 / 0.569 / 0.600"],
          ["Component", "recall@5 with typos (15 % of words, seed 42)", "0.547", "0.656"],
          ["End-to-end", "Faithfulness (llama3.2:3b judge)", "0.786 (11 of 14)",
           "0.714 (10 of 14)"],
          ["End-to-end", "Abstention correctness (12 unanswerable); citation validity",
           "1.00; 1.00", "1.00; 1.00"],
          ["End-to-end", "Latency p50 / p95", "2.24 / 7.03 s", "2.43 / 6.69 s"],
      ], [1.0, 3.1, 1.5, 1.5]),
      p("Files: eval/results/cluster-m1/eval/20261128T133413Z-baseline-cluster.json and "
        "eval/results/final-44-summary.md. Cluster recall is lower because the cluster runs use "
        "the golden set after five fee questions were re-labelled to Batch B's 2027-28 schedule, "
        "and the suite ran before Batch B was ingested (as the C1 comparison requires). "
        "<b>Judge agreement:</b> the judge matched our 8 hand labels 6 times (75 %), one error "
        "each way. <b>Stochasticity:</b> with the Ollama seed, temperature 0.2 and the typo seed "
        "fixed, two full runs gave identical retrieval, abstention, citation and faithfulness "
        "numbers; only timings moved (embedding +5.63 ms, p50 +0.24 s, p95 +5.40 s), from load "
        "on the shared GPU. Between our two laptops' clusters (NVIDIA and AMD GPUs) every "
        "retrieval metric agrees exactly; a few individual answers differ.",
        ParagraphStyle("bodytop2", parent=BODY, spaceBefore=5))]

# --- Part C --------------------------------------------------------------------------
S += [p("Part C. Change experiment and release gate", H2),
      p("<b>C1.</b> The plan's change, chunks of 200/40, lost recall, as did every chunking "
        "variant, so the measured change is top_k 5 to 6 (decision R10b). all-minilm is the "
        "deliberately bad candidate."),
      table([
          ["Candidate", "Env", "recall@5", "MRR", "Faithfulness", "Answered", "p50 s", "Gate"],
          ["Baseline (150/30, nomic-embed-text, top_k 5)", "cluster", "0.562", "0.465",
           "0.786", "14", "2.24", "n/a"],
          ["<b>top_k 6</b>", "cluster", "0.562", "0.465", "0.714", "14", "2.44", "<b>PASS</b>"],
          ["all-minilm", "cluster", "0.469", "0.438", "0.667", "12", "0.08", "<b>FAIL</b>"],
          ["chunks 200/40", "local", "0.641 (base 0.688)", "0.552", "0.733", "", "2.38", "FAIL"],
          ["overlap 40", "local", "0.625", "0.544", "0.812", "", "2.24", "FAIL"],
      ], [2.0, 0.65, 0.95, 0.55, 0.85, 0.8, 0.55, 0.6]),
      p("top_k 6 leaves the top five unchanged, so every retrieval metric is identical; the "
        "difference is only end-to-end. On both members' clusters it declined q41 (semester "
        "freeze), which the baseline answered with the right chunk at rank 1: the sixth passage "
        "was loosely related and llama3.2:3b declined, the safe failure. It answered q26 and q43, "
        "which the baseline declined, with mixed support.",
        ParagraphStyle("bodytop3", parent=BODY, spaceBefore=5)),
      p("<b>C2.</b> config/gate.yaml, the same text in the ragops-gate ConfigMap (a test fails if "
        "they differ); scripts/gate.py exits 0 (release), 1 (reject) or 2 (unusable input)."),
      table([
          ["Rule", "Threshold", "Justification"],
          ["recall@5 drop", "at most 0.02", "The brief's rule; two seeded baseline runs differ "
           "by 0.000, so any drop is the change."],
          ["Faithfulness", "at least 0.64", "Lower baseline (0.714 local) minus one judged "
           "answer (1/14): the judge is wrong 2 times in 8, so one verdict can flip."],
          ["p95 latency", "at most 25 s", "Half the 50 s request budget, so a p95 request that "
           "needs its one retry still finishes."],
          ["p50 latency", "at most 1.5x baseline", "Seeded runs differ by 6 % locally, 5.8 % "
           "on the cluster."],
          ["Abstention correctness", "not below baseline", "The brief's rule (baseline 1.00)."],
          ["Citation validity", "at least 0.95", "Carried from the Assignment 02 CI gate."],
      ], [1.4, 1.3, 4.2]),
      p("<b>Release decision: release top_k 6, reject all-minilm.</b> top_k 6 passes every rule "
        "in both environments and keeps retrieval exactly. all-minilm fails the recall rule by "
        "9.4 points on both; it passes the latency rules only because most of its questions are "
        "declined under a relevance floor calibrated for nomic-embed-text. Recorded caution: "
        "top_k 6's faithfulness is one judged answer below the cluster baseline, inside the "
        "gate's margin. <b>C3</b> is the F3 release below.",
        ParagraphStyle("bodytop4", parent=BODY, spaceBefore=5))]

# --- Part D --------------------------------------------------------------------------
S += [p("Part D. Observability and traceability", H2)]
S += bullets(
    "<b>D1 trace record</b> (api/app/services/trace.py, ADR 0005): one JSON line per query with "
    "the trace id, timestamp, query, rewritten query, embedding model, digest and dimension, "
    "collection, every chunk with doc_id, doc_version, superseded, content hash and score, the "
    "filters, reranked order (no reranker), prompt hash, model and parameters, response, "
    "citations, guardrail actions, latency per stage, and cache hit or miss. Standard output "
    "gets it without prompt text; the ragops-results volume gets the full prompt. 369 records "
    "are in traces/.",
    "<b>D2 trace tool</b>: <i>python -m app.tools.trace_show &lt;id&gt;</i> rebuilds the prompt "
    "from the recorded evidence with the production prompt builder and compares its SHA-256 "
    "with the recorded hash: MATCH (f/06).",
    "<b>D3 metrics</b>: /metrics adds a top-1 similarity histogram, injection flags by source "
    "and latency per stage. Over all 369 cluster traces (f/15): abstention rate 0.377, cache "
    "hit rate 0.186, top-1 similarity p50 0.703 (p25 0.603, p75 0.745), 34 injection flags (9 in "
    "chunks, 25 in questions).",
    "<b>D4 guardrail logging</b>: the retrieval rail flags instruction-like text and writes its "
    "action into the trace. With Batch B's b09, <i>flag</i> mode let the planted \"fees are "
    "waived\" through with a valid citation and the cache served it; <i>redact</i> mode removes "
    "the sentence before the prompt and the model declines. The cluster runs redact, and "
    "answers on flagged evidence are never cached (f/11, f/13).",
)
S += [p("<b>D5. Root cause from one trace.</b> Part B's q13, \"What does clause 1.21 of the "
        "academic rules require?\", is declined in every run. From trace "
        "7087caa6dc4949aea29a80263a9e8fb2 alone:"),
      table([
          ["#", "Finding"],
          ["1", "Filters: superseded false, relevance floor 0.65. Not the cause: all five chunks "
                "clear the floor (0.659 to 0.737)."],
          ["2", "Retrieved: the Student Handbook's \"I - ACADEMIC RULES and REGULATIONS\" (0.737), "
                "three prospectus rules pages, the handbook's \"June 2026\" cover chunk."],
          ["3", "Missing: academic-rules-handbook-jun-2026.pdf#0014 \"Attendance Requirements\", "
                "the only chunk that contains \"1.21\"."],
          ["4", "Cause: the dense embedding matched \"academic rules\" to general rules pages; a "
                "clause number carries almost no meaning for nomic-embed-text. The model then "
                "declined correctly from the evidence it had."],
          ["5", "Fix: a lexical (BM25) score fused with the dense one for exact terms. top_k 6 "
                "does not help: its sixth chunk is front matter (trace fa54a26c...)."],
      ], [0.3, 6.6])]

# --- Part E --------------------------------------------------------------------------
S += [p("Part E. Drift and coverage", H2),
      p("<b>E1.</b> eval/live_queries.jsonl: 41 queries, 28 in the golden set's domain and 13 on "
        "topics the corpus or tests do not cover. <b>E2.</b> The nearest golden question per "
        "query by cosine; threshold 0.65 from a sweep (at 0.65, 26 of 28 in-domain and 2 of 13 "
        "off-topic queries reach it; at 0.80 only 10 of 28 in-domain would). The check exits 1 "
        "below 85 %."),
      table([
          ["Run", "Golden questions", "Covered", "Coverage", "Exit / Job", "Evidence"],
          ["Before E4 (cluster)", "35", "28 of 41", "68 %", "1 / Failed", "cluster-m1/06"],
          ["After E4 (cluster)", "44", "36 of 41", "88 %", "0 / Complete", "cluster-m1/07"],
          ["Before, after 7, after 9 (local)", "27, 34, 36", "28, 34, 36", "68, 83, 88 %",
           "1, 1, 0", "eval/results/*coverage*"],
      ], [2.0, 1.1, 0.9, 0.95, 1.0, 1.4]),
      p("Uncovered before E4: counselling, library, sports and transport (2 each), attendance, "
        "cafeteria, course repeat, exam conduct and IT accounts (1 each). <b>E4</b> added nine "
        "golden questions from those topics (six answered by Batch B, three unanswerable); five "
        "queries stay uncovered. <b>E3 data drift:</b> after Batch B, recall@5 fell from 0.857 "
        "to 0.714 although retrieval had not changed: five golden questions still cited the "
        "2026-27 fee page that Batch B had superseded. After re-labelling them, recall@5 rose "
        "from 0.781 to 0.906 on the 44-question set (eval/results/e3-drift.md). When ingestion "
        "archives a version, the golden questions that cite it must be re-labelled in the same "
        "change, or the gate measures the past.",
        ParagraphStyle("bodytop5", parent=BODY, spaceBefore=5))]

# --- Part F --------------------------------------------------------------------------
S += [p("Part F. Kubernetes", H2),
      table([
          ["Item", "What runs", "Evidence"],
          ["F1", "api Deployment (3 replicas, HPA) and Service; chroma StatefulSet with a PVC; "
                 "the data lake on PVC ragops-data, results and traces on ragops-results.",
           "f/00-kubectl-get-all.txt"],
          ["F2", "Ingestion Job and weekly CronJob (the only Chroma writer); the suite and gate "
                 "as one Job that fails when the gate fails; gate thresholds in ConfigMap "
                 "ragops-gate: Failed, edit, Complete with the same image.",
           "cluster-m1/03-05, f/03"],
          ["F3", "api-candidate Deployment, Service and collection per candidate; release by "
                 "rolling update (maxUnavailable 0); all-minilm stopped by the gate and never "
                 "rolled out; a bad release reversed by rollout undo, after which a trace shows "
                 "rahbar-k6 and nomic-embed-text 0a109f422b47.", "f/14-release-rollout.txt"],
          ["F4", "Traces on standard output (kubectl logs) and the volume; /metrics through "
                 "kubectl port-forward.", "f/05, f/07, f/08"],
          ["F5", "Requests and limits from kubectl top during ingestion, an eval run and an "
                 "82-question burst (table below).", "f5/resources.md"],
      ], [0.45, 4.9, 1.55]),
      Spacer(1, 5),
      table([
          ["Workload", "Peak CPU", "Peak memory", "Requests", "Limits"],
          ["api (each of 3), api-candidate", "87m, 96m", "74Mi, 72Mi", "100m / 160Mi",
           "500m / 320Mi"],
          ["chroma (4 collections)", "16m", "156Mi", "50m / 192Mi", "500m / 512Mi"],
          ["indexer Job, CronJob, candidate index Jobs", "1381m", "1073Mi (OCR peak 1159Mi)",
           "500m / 1280Mi", "2 / 1792Mi"],
          ["eval Job (suite), coverage Job", "91m", "93Mi", "100m / 128Mi", "500m / 256Mi"],
          ["gate Job", "0.1 s CPU", "18 MiB", "50m / 64Mi", "250m / 128Mi"],
      ], [2.4, 0.9, 1.5, 1.05, 1.05]),
      p("A fresh namespace reaches a completed first ingestion (803 chunks) in 4 min 53 s with "
        "<i>kubectl apply -k k8s/overlays/dev</i> (k8s/README.md). Cluster failures found and "
        "fixed (docs/failure-log.md): the provisional 0.95 near-duplicate threshold quarantined "
        "a real document (now 0.98); the planted b09 claim was served from the cache; a release "
        "served the previous configuration's cached answers (cache now keyed by configuration); "
        "a failed ingestion attempt left no logs; two overlapping ingestion runs broke each "
        "other (lake lock); CoreDNS lacked host.minikube.internal on a re-created cluster.",
        ParagraphStyle("bodytop6", parent=BODY, spaceBefore=5))]

# --- Q4 ------------------------------------------------------------------------------
S += [p("4. Short answers", H1),
      p("<b>(a) Which check caught the most, and what was not caught?</b> Uniqueness: it was the "
        "only failing check for three documents (exact copies b02 and b04, near duplicate b05). "
        "Completeness also failed three, but two of them also failed quality. Not caught: the "
        "injected instruction in b09, which is well formed, complete, unique and current. Only "
        "the query-time rail acts on it, and in flag mode a planted claim reached a user. Running "
        "the same instruction-pattern rail as a fifth check at verification would quarantine it "
        "before it is embedded."),
      p("<b>(b) A module metric that looked fine when a later one did not.</b> all-minilm has the "
        "better module gap (0.585 against 0.392, because its unrelated pairs sit near 0.07), yet "
        "its recall@5 is 9.4 points lower and it answers 12 questions instead of 14. The gap "
        "measures separation of easy pairs; retrieval needs the right chunk to beat near-misses "
        "from the same handbook, and all-minilm's similarities (top-1 mean 0.58) fall below a "
        "relevance floor calibrated for nomic-embed-text."),
      p("<b>(c) Archive or delete old versions?</b> We archive: a superseded version moves to "
        "archive/&lt;doc_id&gt;/&lt;version&gt;/ and stays in Chroma with superseded true. "
        "Deleting would break rollback (pipeline.ops restore: 10 metadata updates, 0 "
        "re-embeddings), questions about an older version (which the superseded filter answers), "
        "and reproducibility: a trace names doc_version and content hash, which could no longer "
        "be checked against a source. Deletion is right only for a document that must not be "
        "served; the prune step then leaves 0 orphan chunks."),
      p("<b>(d) The metric we trust least.</b> Faithfulness. The judge is the same 3B model that "
        "writes the answers, agreed with our hand labels 6 times in 8, sees every retrieved "
        "passage rather than only the cited ones (lenient), and is computed over 11 to 15 "
        "answers, so one verdict moves it by 7 points. Seeded runs agree exactly, which shows the "
        "judge is repeatable, not that it is right. Local p95 latency comes second: it swung "
        "from 3 s to 32 s on the same code."),
      p("<b>(e) The paper idea hardest to apply.</b> Traceability: tracing every query to the exact "
        "data version. The trace must hold the prompt, but our Assignment 02 governance keeps "
        "prompts out of INFO logs, so the record is split (stdout without prompt text, the volume "
        "with it, joined by a prompt hash the trace tool verifies). A model name is not a "
        "version, so we record Ollama's digest. A configuration release changes what an answer "
        "means without any data change, so the cache, which the paper does not discuss, is keyed "
        "by configuration as well as index version."),
      p("<b>(f) Which Kubernetes object carries which responsibility?</b>"),
      table([
          ["Object", "RAGOps responsibility"],
          ["Job indexer, CronJob reindex (concurrencyPolicy Forbid), lake lock",
           "The only writer to Chroma: ingest, verify, update the lake and the retrieval source, "
           "one run at a time."],
          ["NetworkPolicy chroma", "Only api, api-candidate, indexer and eval pods reach Chroma; "
           "only the indexer image has write code."],
          ["PVC ragops-data / ragops-results", "The data lake (raw, quarantine, archive) / "
           "results, gate decisions and traces; both survive restarts."],
          ["ConfigMap ragops-gate / rahbar-config", "Every threshold, changed without a "
           "rebuild / the embedding pin shared by the writer and the readers."],
          ["Deployment and Service api-candidate", "The candidate under test, with its own "
           "collection."],
          ["Deployment api (maxUnavailable 0, readiness on the pin)", "Controlled release and "
           "rollout undo; readiness refuses a mismatched index."],
          ["Job ragops-eval, ragops-gate, ragops-coverage", "Offline testing, the release decision "
           "and coverage; each Job fails when its check fails."],
      ], [2.6, 4.3])]

# --- Contribution and AI ---------------------------------------------------------------
S += [p("5. Contributions and AI statement", H1),
      table([
          ["Member", "Work"],
          ["M. Abdul Rehman (24I-3001)", "Data lake, verification (quality, completeness, "
           "recency), incremental sync, archive and restore, lake lock, Batch B (A); golden set, "
           "three-level suite, judge agreement, stochasticity (B); change experiment (C1); live "
           "log, coverage check, drift, closing the gap (E); eval and coverage Jobs (F2 swap); "
           "D5; 4 hand-written golden questions and 8 reviews; report sections A, B, C1, E and "
           "Q4 a, b, d."],
          ["M. Tahir Habib (24I-3087)", "Uniqueness check and its threshold (A1 swap); trace "
           "record, trace tool, metrics, summary, retrieval rail (D1-D4); release gate, config "
           "and ConfigMap (C2); PVCs, Jobs, candidate release, NetworkPolicy, eval image, "
           "resources, k8s/README.md (F, C3); cluster runs of A, B, C and F; 4 hand-written "
           "golden questions and 8 reviews; report sections C2, D, F and Q4 c, e, f."],
      ], [1.6, 5.3]),
      Spacer(1, 6),
      p("<b>AI statement.</b> We used Claude Code (Anthropic) to draft code, tests, manifests, "
        "synthetic golden questions and report text, under our direction. Each use is logged "
        "with what we changed in docs/AI-USAGE.md. The hand-written questions, the hand labels, "
        "the reviews of synthetic questions, every design decision and the screenshots are our "
        "own; every number was produced by our own runs.")]

# --- Appendix ------------------------------------------------------------------------
APPENDIX = [
    ("A", "A-unchanged-corpus.png", "A second ingestion on an unchanged corpus: "
     "kubectl create job --from=cronjob/reindex, then its logs; \"embedded\": 0, 803 unchanged."),
    ("A, F", "F2-ingestion-job-logs-a.png", "Batch B through the ingestion Job: the verification "
     "report, pass or fail per check with reasons (page 1 of 2). Also F: a completed ingestion Job."),
    ("A, F", "F2-ingestion-job-logs-b.png", "The same, page 2: 6 quarantined, 21 embedded, 793 "
     "unchanged."),
    ("B, F", "B-eval-job-summary-and-gate.png", "kubectl logs job/ragops-eval (from kubectl "
     "apply -f k8s/eval-job.yaml): the three-level summary for top_k 6 and the gate, GATE PASS."),
    ("B, F", "F2-eval-job-logs.png", "A completed suite Job for the baseline: three levels and "
     "the stochasticity of two seeded runs."),
    ("C2", "C2-gate-fail.png", "The release gate rejecting all-minilm: recall@5 drops 9.4 points; "
     "exit code 1."),
    ("C2", "C2-gate-pass.png", "The release gate passing top_k 6; exit code 0."),
    ("D1", "D1-trace-record-a.png", "One full trace record from standard output (page 1 of 3)."),
    ("D1", "D1-trace-record-b.png", "The same trace record, page 2."),
    ("D1", "D1-trace-record-c.png", "The same trace record, page 3."),
    ("D2", "D2-trace-tool-a.png", "The trace tool for the same trace id: chunks, versions, scores "
     "and filters (page 1 of 2)."),
    ("D2", "D2-trace-tool-b.png", "The prompt rebuilt from the trace; prompt hash MATCH."),
    ("E", "E-coverage-before.png", "Coverage before E4: 28 of 41 (68 %), uncovered topics, FAIL; "
     "the Job fails."),
    ("E", "E-coverage-after.png", "Coverage after E4: 36 of 41 (88 %), PASS; the Job completes."),
    ("F", "F1-get-all-a.png", "kubectl get all,pvc,configmap,cronjob,job -n rahbar (page 1 of 2)."),
    ("F", "F1-get-all-b.png", "The same, page 2."),
    ("F", "F2-gate-configmap-a.png", "The gate Job Failed with max_drop 0.02."),
    ("F", "F2-gate-configmap-b.png", "After editing ragops-gate (max_drop 0.10), the same Job and "
     "image: Complete, GATE PASS."),
    ("F", "F3-rollout-status.png", "Releasing top_k 6 to the live Deployment: kubectl rollout "
     "status."),
    ("F", "F3-bad-release.png", "A bad release (all-minilm) pushed on purpose; its trace shows "
     "rahbar-minilm and all-minilm."),
    ("F", "F3-rollout-undo.png", "kubectl rollout undo; a new trace shows the previous collection "
     "rahbar-k6 and embedding nomic-embed-text 0a109f422b47."),
]

S += [PageBreak(), p("Appendix: screenshots", H1),
      p("Each screenshot shows the command and its uncropped output in the terminal, from our "
        "own clusters (Member 1: Windows PowerShell; Member 2: Konsole). The plain text of each "
        "run is in eval/results/cluster-m1/ and docs/report/screenshots/transcripts/.")]
for n, (label, file, text) in enumerate(APPENDIX, start=1):
    path = SHOTS / file
    from PIL import Image as PILImage
    w, h = PILImage.open(path).size
    width = WIDTH
    height = width * h / w
    S.append(KeepTogether([p(f"<b>Screenshot {n} ({label}).</b> {text}", CAPTION),
                           Image(str(path), width=width, height=height), Spacer(1, 10)]))

doc = SimpleDocTemplate(str(OUT), pagesize=LETTER, leftMargin=inch, rightMargin=inch,
                        topMargin=inch, bottomMargin=inch,
                        title="RAGOps for RAHBAR: Assignment 03 report",
                        author="M. Abdul Rehman, M. Tahir Habib")
doc.build(S, onFirstPage=footer, onLaterPages=footer)
print(f"wrote {OUT}")
