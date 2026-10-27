#!/usr/bin/env bash
# Start the local embedding server, wait for it, then run the API.
set -euo pipefail

ollama serve &
until curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; do sleep 1; done
echo "ollama ready (nomic-embed-text for query embeddings)"

# Render provides $PORT; default to 8000 for local `docker run`.
exec uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
