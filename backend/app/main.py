import json
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .answers import get_answer, save_answer
from .config import settings
from .db import init_db, pool
from .rag.answer import Answer, answer_question, stream_answer
from .tenant import TenantProfile, list_tenants, load_tenant

logger = logging.getLogger("civicllm")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="CivicLLM", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    tenant: str = "austin"
    mode: str = "public"  # "staff" | "public"
    message: str = Field(min_length=1, max_length=2000)
    provider: str | None = None  # override LLM_PROVIDER per request (demo toggle)
    language: Literal["en", "es"] = "en"


def _load_tenant_or_404(req: ChatRequest) -> TenantProfile:
    try:
        tenant = load_tenant(req.tenant)
    except KeyError:
        raise HTTPException(404, f"Unknown tenant: {req.tenant}")
    if req.mode not in tenant.modes:
        raise HTTPException(400, f"Unknown mode '{req.mode}' for tenant '{req.tenant}'")
    return tenant


def _tenant_freshness(tenant_id: str) -> str | None:
    """Human corpus-freshness label captured at ingest time (tenants.config)."""
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT config->>'freshness' FROM tenants WHERE id=%s", (tenant_id,)
        ).fetchone()
    return row[0] if row else None


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "tenants": list_tenants()}


@app.get("/api/tenants/{tenant_id}")
async def tenant_info(tenant_id: str) -> dict:
    try:
        t = load_tenant(tenant_id)
    except KeyError:
        raise HTTPException(404, f"Unknown tenant: {tenant_id}")
    return {
        "id": t.id,
        "display_name": t.display_name,
        "corpus_name": t.corpus_name,
        "modes": sorted(t.modes),
        "languages": t.languages,
        "example_questions": t.example_questions,
        "example_questions_es": t.example_questions_es,
        "scope_statement": t.scope_statement,
        "scope_statement_es": t.scope_statement_es,
        "freshness": _tenant_freshness(t.id),
        "channels": [asdict(c) for c in t.channels],
    }


@app.get("/api/answers/{answer_id}")
async def answer_permalink(answer_id: str) -> dict:
    record = get_answer(answer_id)
    if record is None:
        raise HTTPException(404, f"Unknown answer id: {answer_id}")
    return record


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict:
    tenant = _load_tenant_or_404(req)
    result = await answer_question(tenant, req.mode, req.message, req.provider, req.language)
    save_answer(req.tenant, req.mode, req.language, req.message, result)
    return asdict(result)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    tenant = _load_tenant_or_404(req)  # tenant/mode errors are normal HTTP, pre-stream

    async def events():
        try:
            async for kind, payload in stream_answer(
                tenant, req.mode, req.message, req.provider, req.language
            ):
                if isinstance(payload, Answer):
                    save_answer(req.tenant, req.mode, req.language, req.message, payload)
                    yield _sse("final", asdict(payload))
                elif kind == "delta":
                    yield _sse("delta", {"text": payload})
        except Exception:  # terminal SSE error frame instead of a broken stream
            # Never leak internals (SDK auth errors, tracebacks) to end users;
            # the detail goes to the server log, the client gets a stable code.
            logger.exception("chat stream failed")
            yield _sse("error", {"code": "generation_failed"})

    return StreamingResponse(events(), media_type="text/event-stream")
