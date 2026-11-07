# The api image (§4.7, §6). Build context: api/. Reads the index, never writes it.
FROM python:3.12.11-slim

# No .pyc writes (the root filesystem is read-only on the cluster), unbuffered logs, and a
# HOME under /tmp, the one writable path (an emptyDir in the Deployment).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin rahbar
COPY app ./app

# Numeric, so the pod's runAsNonRoot check can verify it without reading /etc/passwd.
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
