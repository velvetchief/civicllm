# API Contract v2 — answer anatomy, streaming, permalinks, i18n

Shared contract for the backend and frontend workstreams. Do not deviate without
updating this file.

## POST /api/chat  (kept, non-streaming — used by eval + fallback)

Request:
```json
{
  "tenant": "austin",
  "mode": "public" | "staff",
  "message": "…",
  "provider": "ollama" | "anthropic" | null,
  "language": "en" | "es"        // NEW, default "en"
}
```

Response (Answer):
```json
{
  "answer_id": "a_8f3k2p",           // NEW: permalink id, persisted
  "text": "…markdown-lite…",         // key figures wrapped in **bold** by the model
  "grounded": true,
  "refused": false,
  "provider": "ollama",
  "disclaimer": "…",                 // mode disclaimer (may be empty)
  "sources": [
    {
      "number": 1,
      "title": "§ 25-2-492 - SITE DEVELOPMENT REGULATIONS.",
      "hierarchy": ["TITLE 25…", "…"],
      "section_ref": "§ 25-2-492",
      "source_url": "https://library.municode.com/…",
      "excerpt": "first 300 chars…",
      "quote": "full chunk text, capped at 2000 chars"   // NEW: inline verification
    }
  ],
  "related": [                        // NEW: top 3 non-cited rerank candidates
    {"title": "…", "section_ref": "§ 25-2-…", "source_url": "…"}
  ],
  "next_steps": [                     // NEW: always present on refusal; may be
    {"label": "Book a free 20-minute zoning appointment",          // present otherwise
     "detail": "Virtual (Teams) or in person at the PDC",
     "url": "https://www.austintexas.gov/development-services/schedule-appointment-permitting-and-development-center-pdc"}
  ]
}
```

`text` markdown-lite: ONLY `**bold**` and newlines are rendered; everything else is
plain text. Citations appear inline as `[n]` and map to `sources[].number`.

## POST /api/chat/stream  (NEW — SSE)

Same request body. Response `Content-Type: text/event-stream`, events in order:

```
event: delta      data: {"text": "…token(s)…"}     (repeated; only the answer text)
event: final      data: {…complete Answer JSON as above…}
event: error      data: {"message": "…"}           (terminal, instead of final)
```

Notes: deltas are raw text fragments of the eventual `text` field. Rerank/guard
phases emit no deltas (frontend shows its own progress copy until first delta). If
the pipeline refuses, no deltas are sent — just `final` with `refused: true`.

## GET /api/answers/{answer_id}  (NEW)

Returns `{"question": "…", "mode": "public", "language": "en", "created_at": "…",
"answer": {…Answer…}}`. 404 if unknown. Backed by new `answers` table
(id text pk, tenant_id, mode, language, question, payload jsonb, created_at).

## GET /api/tenants/{id}  (extended)

```json
{
  "id": "austin",
  "display_name": "…",
  "corpus_name": "…",
  "modes": ["public", "staff"],
  "languages": ["en", "es"],                        // NEW
  "example_questions": ["…"],
  "example_questions_es": ["…"],                    // NEW
  "scope_statement": "I answer questions about …",  // NEW (en)
  "scope_statement_es": "…",                        // NEW
  "freshness": "Code current through Supp. No. 173 (Ord. 20260122-059, eff. Feb 2, 2026)",  // NEW, from ingest
  "channels": [ {"label": "…", "detail": "…", "url": "…"} ]   // NEW: handoff channels
}
```

`freshness` is captured at ingest time from the Municode job `BannerText` and stored
in `tenants.config` jsonb; null if never ingested.

## Language behavior

`language: "es"` → generation instructed to answer in plain Spanish; citations,
section refs, and quoted code text stay in English (the legal text is English —
do not translate quotes). Refusal text + next_steps rendered from tenant YAML
(which carries `label_es`/`detail_es` variants).

## Frontend routes

- `/` — main app (modes, toggles, chat)
- `/a/[id]` — permalink page: fetches GET /api/answers/{id}, renders the same
  answer anatomy read-only + "Ask a follow-up" link to `/`.

## Non-negotiables (both sides)

- Backend: pyright + ruff clean; `uv run python -m eval.run_eval austin ollama`
  still 10/10 (eval calls answer_question directly — keep its signature working).
- Frontend: `npm run typecheck` clean; only `**bold**`+newlines rendered from model
  text (no raw HTML injection); aria-live="polite" region announces streaming
  status; WCAG 2.1 AA-minded semantics throughout.
