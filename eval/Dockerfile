# The eval image (RAGOps B, C2, E, F2): the Part B suite, the coverage check and the release
# gate, for the eval Job (k8s/eval-job.yaml) and the gate Job (k8s/gate-job.yaml).
# Build context: the REPOSITORY ROOT, because eval/suite.py imports the api package (it runs
# the api's own retriever code for the component level):
#   docker build -t rahbar-eval:dev -f eval/Dockerfile .
# What goes in is the allowlist in eval/Dockerfile.dockerignore (BuildKit reads the ignore
# file named after the Dockerfile before the context's own .dockerignore).
#
# Layout in the image, the same as the repository, so every script's relative imports work:
#   /app/api/app   /app/eval/*.py, golden.jsonl, embedding_pairs.jsonl, live_queries.jsonl
#   /app/scripts/gate.py   /app/config/gate.yaml (the ConfigMap's copy is mounted at /config)
FROM python:3.12.16-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp

WORKDIR /app
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*
COPY api/requirements.txt ./api/requirements.txt
# pyyaml: the gate config, golden.yaml and fixtures. Same pin as indexer/requirements.txt.
RUN pip install -r api/requirements.txt pyyaml==6.0.2 \
 && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin rahbar
COPY api/app ./api/app
COPY eval/suite.py eval/run_eval.py eval/ragops_metrics.py eval/query_coverage.py ./eval/
COPY eval/golden.jsonl eval/embedding_pairs.jsonl eval/live_queries.jsonl ./eval/
COPY scripts/gate.py ./scripts/gate.py
COPY config/gate.yaml ./config/gate.yaml

USER 10001
# The Jobs set their own command; this one only proves the image works.
CMD ["python", "eval/suite.py", "--help"]
