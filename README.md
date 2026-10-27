# CivicLLM

CivicLLM answers questions from an institution's official documents. Every answer cites the section it came from. If the documents do not cover a question, it says so instead of guessing.

It can run fully private on local weights through Ollama, or on Claude Sonnet for a hosted demo. Two city codes are set up as tenants: the City of Austin Land Development Code (Title 25) and the City of Brownsville Unified Development Code. Both are public documents, pulled from Municode.

## How it works

```
Next.js UI (resident and staff modes)
        |
FastAPI  /api/chat
        |
Hybrid retrieval ---- Postgres + pgvector (vector + full-text, fused with RRF)
        |                       ^
LLM rerank                      | ingestion: Municode API -> parse (tables
        |                       |   linearized) -> chunk -> embed
Grounded generation
  - Claude Sonnet (hosted default)
  - Ollama (local weights, for on-prem)
        |
Guardrails: refusal sentinel, citation-required check,
            retrieval score floor, per-mode disclaimers
```

Each answer passes three guards:

1. The top retrieved section must clear a score floor. If it does not, the system refuses before it calls the model.
2. If the model says the documents do not cover the question, through the sentinel or a plain decline, the answer becomes a refusal.
3. The answer must cite retrieved sections. If the model leaves out the citation markers, the figures in the answer must appear word for word in a retrieved section, and that section becomes the citation. An answer that passes neither check is marked ungrounded.

During streaming, the first characters are held back so the refusal sentinel never reaches the browser. A refusal always points the user to a person who can help.

Everything specific to one institution lives in `backend/app/tenants/<id>.yaml`: personas, disclaimers, example questions, and the Municode source.

## Run it

```bash
cp .env.example .env                     # set ANTHROPIC_API_KEY, or LLM_PROVIDER=ollama
docker compose up -d                     # Postgres + pgvector
ollama pull nomic-embed-text             # embeddings run locally in both modes
ollama pull qwen2.5:7b-instruct          # only needed for LLM_PROVIDER=ollama

cd backend
uv sync
uv run python -m ingest.pipeline austin  # fetch, chunk and embed the code
uv run uvicorn app.main:app --port 8000

cd ../frontend
npm install && npm run dev               # UI at http://localhost:3000
```

## Check the answers

```bash
cd backend
uv run python -m eval.run_eval austin            # golden set, default provider
uv run python -m eval.run_eval austin anthropic  # same set against Claude
```

Each tenant has a golden set of 10 questions with known answers. A case passes when the correct figure appears, the governing section is cited, and out-of-corpus questions are refused.

Add `--out` to save every question, answer, cited source and failure reason as JSON:

```bash
uv run python -m eval.run_eval austin ollama --out eval/results/austin-qwen2.5-7b.json
```

The saved runs on Qwen 2.5 7B are in [backend/eval/results](backend/eval/results/). Brownsville scored 9 of 10. In the miss, the answer passed the content check but cited two sources as `[2, 5]`, and the grounding check reads only one number per bracket. Austin scored 8 of 10. The model gave the wrong figures for the SF-3 front yard setback and the SF-3 impervious cover limit, and for impervious cover it also cited the wrong section. An earlier run, which was not saved, scored 10 of 10 and 9 of 10.

Unit tests cover the citation guards, streaming guards, ingestion parsing, and retrieval with rerank:

```bash
cd backend && uv run pytest
cd frontend && npm test
```

CI runs ruff, pyright and pytest on the backend, and tsc and vitest on the frontend.

## Add a new institution

1. Copy `backend/app/tenants/austin.yaml` to `<new>.yaml`. Set the personas, disclaimers and example questions.
2. Point ingestion at the source. Any city on Municode works without code changes. Other sources implement the same fetch, parse and chunk steps.
3. Add `backend/eval/golden_<new>.jsonl` with at least 10 known-answer questions.
4. Run `uv run python -m ingest.pipeline <new>`, then the eval.

## Deploy

`render.yaml` defines the backend as a Docker service on Render. Postgres with pgvector can be any managed host. Set `ANTHROPIC_API_KEY` and `DATABASE_URL` as secrets in the dashboard, and set `CORS_ORIGINS` to your frontend's origin.

## Design notes

`docs/` holds the API contract, the product and UX research, and a red-team review. The review lists 41 findings. All 41 are fixed.
