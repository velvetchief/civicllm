from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from .config import settings

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tenants (
    id           text PRIMARY KEY,
    display_name text NOT NULL,
    config       jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS documents (
    id           bigserial PRIMARY KEY,
    tenant_id    text NOT NULL REFERENCES tenants(id),
    source_id    text NOT NULL,        -- stable id in the source system (e.g. Municode node id)
    title        text NOT NULL,
    hierarchy    jsonb NOT NULL DEFAULT '[]'::jsonb,  -- e.g. ["Title 25", "Chapter 25-2", ...]
    section_ref  text,                 -- human citation, e.g. "§ 25-2-492"
    source_url   text,
    content      text NOT NULL,
    content_hash text NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, source_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    id          bigserial PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id   text NOT NULL REFERENCES tenants(id),
    chunk_index int NOT NULL,
    content     text NOT NULL,
    embedding   vector(768),
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE TABLE IF NOT EXISTS answers (
    id         text PRIMARY KEY,          -- short permalink id, e.g. "a_8f3k2p9x1c"
    tenant_id  text NOT NULL REFERENCES tenants(id),
    mode       text NOT NULL,
    language   text NOT NULL,
    question   text NOT NULL,
    payload    jsonb NOT NULL,            -- the full Answer JSON as served
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_tenant_idx ON chunks (tenant_id);
-- HNSW index for vector search (safe on empty table; builds incrementally)
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks
    USING hnsw (embedding vector_cosine_ops);
"""


def _configure(conn) -> None:
    # The extension must exist before register_vector can look up the type OID,
    # and this hook runs on every new connection — including the very first one.
    # Advisory lock: IF NOT EXISTS still races when the pool opens connections
    # concurrently.
    conn.execute("SELECT pg_advisory_xact_lock(42)")
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)


pool = ConnectionPool(
    settings.database_url, min_size=1, max_size=8, open=False, configure=_configure
)


def init_db() -> None:
    pool.open()
    with pool.connection() as conn:
        conn.execute(SCHEMA)  # type: ignore[arg-type]
