"""Answer persistence: every answered/refused chat gets a short permalink id, so
two reviewers (or a 311 agent and a caller) can share one identical answer."""

import secrets
from dataclasses import asdict

from psycopg.types.json import Jsonb

from .db import pool
from .rag.answer import Answer


def _new_id() -> str:
    return "a_" + secrets.token_urlsafe(8)[:10]  # 10 url-safe random chars


def save_answer(
    tenant_id: str, mode: str, language: str, question: str, answer: Answer
) -> str:
    """Assigns answer.answer_id and persists the full Answer JSON. Returns the id."""
    answer.answer_id = _new_id()
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO answers (id, tenant_id, mode, language, question, payload)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (answer.answer_id, tenant_id, mode, language, question, Jsonb(asdict(answer))),
        )
    return answer.answer_id


def get_answer(answer_id: str) -> dict | None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT question, mode, language, payload, created_at FROM answers WHERE id=%s",
            (answer_id,),
        ).fetchone()
    if row is None:
        return None
    question, mode, language, payload, created_at = row
    return {
        "question": question,
        "mode": mode,
        "language": language,
        "created_at": created_at.isoformat(),
        "answer": payload,
    }
