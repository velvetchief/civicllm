"""Shared fixtures. All tests are pure-logic unit tests: no database, no network,
no LLM. External services (Postgres, Ollama, Anthropic) are never touched — the
psycopg pool in app.db is created with open=False and stays closed.
"""

import pytest

from app.rag.retrieve import RetrievedChunk
from app.tenant import Channel, Mode, TenantProfile


def make_chunk(
    chunk_id: int,
    content: str,
    *,
    document_id: int | None = None,
    title: str = "Section",
    section_ref: str | None = None,
    score: float = 0.05,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id if document_id is not None else chunk_id,
        title=title,
        hierarchy=["Title 25", "Chapter 25-2", title],
        section_ref=section_ref,
        source_url=f"https://example.test/code#{chunk_id}",
        content=content,
        score=score,
    )


@pytest.fixture
def tenant() -> TenantProfile:
    return TenantProfile(
        id="testville",
        display_name="City of Testville",
        corpus_name="Testville Land Development Code",
        citation_noun="section",
        source_link_label="View on Municode",
        modes={
            "public": Mode(
                persona="You help residents.",
                disclaimer="Not legal advice.",
                disclaimer_es="No es asesoría legal.",
            ),
            "staff": Mode(persona="You assist permitting staff.", disclaimer="Verify before use."),
        },
        channels=[
            Channel(
                label="Call Development Services",
                detail="Mon-Fri 8-5",
                url="https://example.test/contact",
                label_es="Llame a Servicios de Desarrollo",
                detail_es="Lun-Vie 8-5",
            )
        ],
    )
