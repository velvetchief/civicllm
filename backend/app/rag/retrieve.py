"""Hybrid retrieval: vector similarity + full-text search, fused with Reciprocal
Rank Fusion. Legal/policy corpora need both arms — residents ask semantically
("how tall can my house be") while staff cite lexically ("25-2-492 SF-3")."""

import re
from dataclasses import dataclass

from ..db import pool
from ..providers import get_embedder

RRF_K = 60


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    title: str
    hierarchy: list[str]
    section_ref: str | None
    source_url: str | None
    content: str
    score: float


_VECTOR_SQL = """
SELECT c.id FROM chunks c
WHERE c.tenant_id = %s AND c.embedding IS NOT NULL
ORDER BY c.embedding <=> %s::vector
LIMIT %s
"""

# ts_rank_cd normalization flag 1 = divide by 1 + log(doc length): keyword-dense long
# chunks (e.g. per-district use lists) must not drown short, exact regulation records.
_FTS_SQL = """
SELECT c.id FROM chunks c
WHERE c.tenant_id = %s AND c.tsv @@ websearch_to_tsquery('english', %s)
ORDER BY ts_rank_cd(c.tsv, websearch_to_tsquery('english', %s), 1) DESC
LIMIT %s
"""

# Filter by exact code-token presence, rank semantically: precision from the
# token filter, relevance from the embedding. Keyword-rank ordering here buries
# short records under keyword-dense prose.
_EXACT_SQL = """
SELECT c.id FROM chunks c
WHERE c.tenant_id = %s AND c.content ~* %s AND c.embedding IS NOT NULL
ORDER BY c.embedding <=> %s::vector
LIMIT %s
"""

_STOPWORDS = frozenset(
    "a an and are can class for how i in is it my of on or the to what when where which who why with you your".split()
)


def _keyword_or_query(question: str) -> str:
    """websearch_to_tsquery ANDs every term, so natural questions ('…for a home in
    an SF-3 zone?') often match nothing. This builds a permissive OR query from the
    content words; ts_rank_cd then rewards chunks matching the most terms."""
    words = re.findall(r"[\w-]+", question.lower())
    keywords = [w for w in words if w not in _STOPWORDS and len(w) > 1]
    return " OR ".join(dict.fromkeys(keywords))


def _code_tokens(question: str) -> list[str]:
    """Code-like identifiers (SF-3, MF-4, 25-2-492) are the highest-signal terms in
    an institutional-corpus query — embeddings blur them and stemming mangles them,
    so they get their own exact-match retrieval arm."""
    tokens = re.findall(r"\b(?:[A-Za-z]{1,4}-\d+[A-Za-z]?|\d+(?:-\d+)+)\b", question)
    return list(dict.fromkeys(t.upper() for t in tokens))

_HYDRATE_SQL = """
SELECT c.id, c.document_id, d.title, d.hierarchy, d.section_ref, d.source_url, c.content
FROM chunks c JOIN documents d ON d.id = c.document_id
WHERE c.id = ANY(%s)
"""


async def retrieve(tenant_id: str, query: str, k_per_arm: int, k_final: int) -> list[RetrievedChunk]:
    embedder = get_embedder()
    query_vec = await embedder.embed_query(query)

    with pool.connection() as conn:
        vec_ids = [r[0] for r in conn.execute(_VECTOR_SQL, (tenant_id, query_vec, k_per_arm))]
        fts_ids = [r[0] for r in conn.execute(_FTS_SQL, (tenant_id, query, query, k_per_arm))]
        or_q = _keyword_or_query(query)
        kw_ids = (
            [r[0] for r in conn.execute(_FTS_SQL, (tenant_id, or_q, or_q, k_per_arm))]
            if or_q
            else []
        )
        exact_ids: list[int] = []
        tokens = _code_tokens(query)
        if tokens:
            # Chunks must contain every code token, word-bounded (SF-3 ≠ SF-3C).
            pattern = "".join(rf"(?=.*\m{re.escape(t)}\M)" for t in tokens)
            exact_ids = [
                r[0]
                for r in conn.execute(_EXACT_SQL, (tenant_id, pattern, query_vec, k_per_arm))
            ]

        # Exact code-token matches get triple weight: when a user names a specific
        # district or section, chunks without that identifier are rarely the answer.
        arms = [(vec_ids, 1.0), (fts_ids, 1.0), (kw_ids, 1.0), (exact_ids, 3.0)]
        fused: dict[int, float] = {}
        for ranking, weight in arms:
            for rank, chunk_id in enumerate(ranking):
                fused[chunk_id] = fused.get(chunk_id, 0.0) + weight / (RRF_K + rank + 1)

        top_ids = sorted(fused, key=lambda i: fused[i], reverse=True)[:k_final]
        if not top_ids:
            return []

        rows = conn.execute(_HYDRATE_SQL, (top_ids,)).fetchall()

    by_id = {row[0]: row for row in rows}
    return [
        RetrievedChunk(
            chunk_id=row[0],
            document_id=row[1],
            title=row[2],
            hierarchy=row[3],
            section_ref=row[4],
            source_url=row[5],
            content=row[6],
            score=fused[cid],
        )
        for cid in top_ids
        if (row := by_id.get(cid)) is not None
    ]
