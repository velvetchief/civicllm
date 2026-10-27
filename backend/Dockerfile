# CivicLLM backend for Render (or any Docker host).
# One container runs FastAPI + a local Ollama serving ONLY nomic-embed-text for
# query embeddings (documents are pre-embedded and migrated into Postgres). The
# LLM itself is Claude Sonnet via the Anthropic API — no GPU needed here.
FROM python:3.12-slim

# curl for the Ollama installer + ca-certificates for TLS to the Anthropic API.
# zstd is required by the Ollama installer's extraction step on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates procps zstd \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://ollama.com/install.sh | sh

# uv for locked, reproducible dependency installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first (cached layer) — only the lockfiles bust it.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY . .

# Bake the embedding model into the image so cold starts don't download 270MB.
RUN ollama serve & \
    OLLAMA_PID=$! ; \
    until curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1 ; do sleep 1 ; done ; \
    ollama pull nomic-embed-text ; \
    kill "$OLLAMA_PID"

ENV OLLAMA_BASE_URL=http://127.0.0.1:11434 \
    LLM_PROVIDER=anthropic \
    PYTHONUNBUFFERED=1

CMD ["/app/start.sh"]
