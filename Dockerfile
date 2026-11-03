# AX-NEWS: the backend (it serves the pages and frontend/ too) and its
# workers, in one image. docker-compose.yml runs it twice: `backend` and
# `worker` (deploy/docker/scheduler.py, the systemd timers' work).
FROM python:3.12.14-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
# The translation models run on the CPU: torch without CUDA (some 2 GB
# less), then everything else but the CUDA wheels.
RUN pip install --no-cache-dir torch==2.12.0 --index-url https://download.pytorch.org/whl/cpu \
 && grep -vE '^(nvidia-|cuda-|torch==|triton==)' /tmp/requirements.txt > /tmp/requirements-cpu.txt \
 && pip install --no-cache-dir -r /tmp/requirements-cpu.txt

COPY . /app
RUN useradd --system --home /data --create-home axnews \
 && mkdir -p /var/log/ax-news /data/argos \
 && chown -R axnews /var/log/ax-news /data
USER axnews
# The translation models (deploy/install-argos-models.sh) live in the volume.
ENV HOME=/data/argos ARGOS_HOME=/data/argos AXNEWS_SERVE_STATIC=1 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
