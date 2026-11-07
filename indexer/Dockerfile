# The indexer image (§3.1, §4.2, §6): the only writer to Chroma. Build context: the
# repository root (`docker build -f indexer/Dockerfile .`), because the Job fetches the
# corpus at start-up with corpus/fetch.py and checks it against the committed
# corpus/MANIFEST.md (decision Q4, docs/PIPELINE.md). The PDFs never enter the image.
FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    CORPUS_DIR=/corpus

# OCR for the scanned PDFs (D12). pypdfium2 renders the pages, so no poppler.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin rahbar

WORKDIR /app
COPY indexer/requirements.txt .
RUN pip install -r requirements.txt
COPY indexer/pipeline ./pipeline
COPY corpus/fetch.py corpus/sources.yaml corpus/MANIFEST.md ./corpus/
# The CI e2e-eval job indexes these with CORPUS_DIR=eval/fixtures (D5).
COPY eval/fixtures ./eval/fixtures

USER 10001
# The Job and CronJob override this with the fetch, verify, index chain (k8s/base).
CMD ["python", "-m", "pipeline.run"]
