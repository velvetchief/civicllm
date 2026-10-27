"""Ingestion pipeline: Municode TOC walk -> parse -> chunk -> embed -> upsert.

Content-hash based: unchanged sections are skipped, so re-running against a new
supplement only re-embeds what the city amended. This keeps a
"refresh within 10 business days of code amendments" SLA cheap to honor.
"""

import asyncio
import hashlib
import json
import re

from psycopg.types.json import Jsonb

from app.db import init_db, pool
from app.providers import get_embedder
from app.tenant import TenantProfile

from .municode import MunicodeClient, walk_sections
from .parse import extract_section_ref, html_to_text

CHUNK_CHARS = 4000
CHUNK_OVERLAP = 400
EMBED_BATCH = 16

SECTION_URL = "https://library.municode.com/{state}/{client}/codes/{product_slug}?nodeId={node_id}"


# Municode banner: "Codified through Ordinance No. …, adopted …. (Supp. No. …)".
# Both halves become the human freshness label shown in the product footer.
_BANNER = re.compile(
    r"Codified through\s+(?P<ord>.+?)\.?\s*\((?P<supp>Supp\.?\s*No\.?\s*[^)]*)\)",
    re.IGNORECASE | re.DOTALL,
)


def freshness_label(banner_text: str) -> str | None:
    """Human corpus-freshness label from the Municode latest-job BannerText."""
    text = re.sub(r"<[^>]+>", " ", banner_text)  # banner is occasionally HTML-wrapped
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    m = _BANNER.search(text)
    if not m:
        return text  # unrecognized shape — the raw banner is still a truthful label
    return f"Code current through {m['supp'].strip()} ({m['ord'].strip()})"


# A linearized table record ("SF-3 — MINIMUM LOT SIZE: 5,750; …"). These become
# atomic chunks: short, self-contained, and exactly what district/entity queries
# need. Grouping them dilutes embeddings and buries the one record that answers.
_RECORD = re.compile(r"^[^\n]{1,40} — \S")

# A bare subsection marker on its own paragraph ("A." / "B." / "12.") — Municode's
# formatting for lettered/numbered subsections. Sections that enumerate entities
# (e.g. one zoning district per letter) must split there, or one chunk carries
# several districts and every downstream stage has to fight the mixture.
_SUBSECTION = re.compile(r"^(?:[A-Z]|\d{1,2})\.$")
_MIN_SPLIT_SIZE = 600


def chunk_text(text: str) -> list[str]:
    """Paragraph-aware sliding window; table records are emitted as atomic chunks;
    lettered/numbered subsection markers start a new chunk."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal current, size
        if current:
            chunks.append("\n\n".join(current))
            current, size = [], 0

    for para in paragraphs:
        if _RECORD.match(para) and len(para) > 150:
            flush()
            chunks.append(para)
            continue
        if _SUBSECTION.match(para.strip()) and size >= _MIN_SPLIT_SIZE:
            flush()
        if size + len(para) > CHUNK_CHARS and current:
            chunks.append("\n\n".join(current))
            # Overlap: carry trailing paragraphs into the next chunk.
            tail: list[str] = []
            tail_size = 0
            for p in reversed(current):
                if tail_size + len(p) > CHUNK_OVERLAP:
                    break
                tail.insert(0, p)
                tail_size += len(p)
            current, size = tail, tail_size
        current.append(para)
        size += len(para)
    flush()
    return chunks


async def ingest_municode_tenant(tenant: TenantProfile, force: bool = False) -> dict:
    init_db()
    _upsert_tenant(tenant)

    cfg = tenant.ingest
    client = MunicodeClient()
    product_id, job_id, banner = client.resolve_product(
        cfg["client_name"], cfg["state"], cfg.get("product_name", "Land Development Code")
    )
    print(f"[ingest] product={product_id} job={job_id}")

    freshness = freshness_label(banner)
    if freshness:
        _store_freshness(tenant.id, freshness)
        print(f"[ingest] freshness: {freshness}")

    leaves = walk_sections(client, job_id, product_id, cfg["root_nodes"])
    print(f"[ingest] {len(leaves)} leaf sections in TOC")

    hierarchy_by_id = {n.id: n.hierarchy for n in leaves}
    pending_ids = set(hierarchy_by_id)

    embedder = get_embedder()
    stats = {"sections": 0, "skipped": 0, "chunks": 0}

    # Fetching one leaf returns its whole chunk group; drain pending_ids group by group.
    while pending_ids:
        node_id = next(iter(pending_ids))
        docs = client.content_docs(job_id, product_id, node_id)
        got_any = False
        for doc in docs:
            doc_id = doc["Id"]
            if doc_id not in pending_ids or not (doc.get("Content") or "").strip():
                continue
            got_any = True
            pending_ids.discard(doc_id)
            await _ingest_doc(tenant, cfg, doc, hierarchy_by_id[doc_id], embedder, stats, force)
        if not got_any:
            pending_ids.discard(node_id)  # empty/structural node; don't loop forever
    print(f"[ingest] done: {stats}")
    return stats


async def _ingest_doc(tenant, cfg, doc, hierarchy, embedder, stats, force: bool = False) -> None:
    title = (doc.get("Title") or "").strip()
    text = html_to_text(doc["Content"])
    if not text:
        return
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    source_url = SECTION_URL.format(
        state=cfg["state"].lower(),
        client=cfg["client_name"].lower(),
        product_slug=cfg.get("product_slug", "land_development_code"),
        node_id=doc["Id"],
    )

    with pool.connection() as conn:
        existing = conn.execute(
            "SELECT id, content_hash FROM documents WHERE tenant_id=%s AND source_id=%s",
            (tenant.id, doc["Id"]),
        ).fetchone()
        if existing and existing[1] == content_hash and not force:
            stats["skipped"] += 1
            return

        row = conn.execute(
            """
            INSERT INTO documents (tenant_id, source_id, title, hierarchy, section_ref,
                                   source_url, content, content_hash)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, source_id) DO UPDATE SET
              title=EXCLUDED.title, hierarchy=EXCLUDED.hierarchy,
              section_ref=EXCLUDED.section_ref, source_url=EXCLUDED.source_url,
              content=EXCLUDED.content, content_hash=EXCLUDED.content_hash,
              updated_at=now()
            RETURNING id
            """,
            (
                tenant.id,
                doc["Id"],
                title,
                json.dumps(hierarchy),
                extract_section_ref(title),
                source_url,
                text,
                content_hash,
            ),
        ).fetchone()
        assert row is not None
        document_id = row[0]
        conn.execute("DELETE FROM chunks WHERE document_id=%s", (document_id,))

        # Prefix each chunk with its citation context so embeddings carry the "where".
        crumb = " > ".join(hierarchy[-3:]) if hierarchy else title
        chunks = [f"{crumb}\n\n{c}" for c in chunk_text(text)]

        for batch_start in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[batch_start : batch_start + EMBED_BATCH]
            embeddings = await embedder.embed_documents(batch)
            for j, (content, emb) in enumerate(zip(batch, embeddings)):
                conn.execute(
                    """INSERT INTO chunks (document_id, tenant_id, chunk_index, content, embedding)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (document_id, tenant.id, batch_start + j, content, emb),
                )
        stats["sections"] += 1
        stats["chunks"] += len(chunks)
        if stats["sections"] % 25 == 0:
            print(f"[ingest] {stats['sections']} sections, {stats['chunks']} chunks…")


def _store_freshness(tenant_id: str, label: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE tenants SET config = config || %s WHERE id = %s",
            (Jsonb({"freshness": label}), tenant_id),
        )


def _upsert_tenant(tenant: TenantProfile) -> None:
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO tenants (id, display_name) VALUES (%s,%s)
               ON CONFLICT (id) DO UPDATE SET display_name=EXCLUDED.display_name""",
            (tenant.id, tenant.display_name),
        )


def main() -> None:
    import sys

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv  # re-chunk/re-embed even when content is unchanged
    tenant_id = args[0] if args else "austin"
    from app.tenant import load_tenant

    asyncio.run(ingest_municode_tenant(load_tenant(tenant_id), force=force))


if __name__ == "__main__":
    main()
