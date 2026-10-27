"""Ingestion correctness feeds citation correctness: if a zoning matrix is
linearized wrong, the engine confidently cites the wrong district's numbers.
Covers table linearization (html_to_text), chunking (chunk_text), section-ref
extraction, and the corpus freshness label."""

from ingest.parse import extract_section_ref, html_to_text
from ingest.pipeline import CHUNK_CHARS, CHUNK_OVERLAP, chunk_text, freshness_label


def test_wide_matrix_linearized_column_wise():
    # Miniature § 25-2-492-style matrix: rows = regulations, columns = districts.
    headers = "<th></th><th>SF-1</th><th>SF-2</th><th>SF-3</th><th>MF-1</th><th>MF-2</th><th>MF-3</th>"
    lot = "<td>MINIMUM LOT SIZE</td><td>10,000</td><td>5,750</td><td>5,750</td><td>8,000</td><td>8,000</td><td>8,000</td>"
    height = "<td>MAXIMUM HEIGHT</td><td>35</td><td>35</td><td>35</td><td>40</td><td>60</td><td>60</td>"
    html = f"<table><tr>{headers}</tr><tr>{lot}</tr><tr>{height}</tr></table>"

    text = html_to_text(html)
    records = text.split("\n\n")

    assert len(records) == 6  # one self-contained record per district
    sf3 = next(r for r in records if r.startswith("SF-3"))
    assert "MINIMUM LOT SIZE: 5,750" in sf3
    assert "MAXIMUM HEIGHT: 35" in sf3
    mf2 = next(r for r in records if r.startswith("MF-2"))
    assert "MAXIMUM HEIGHT: 60" in mf2
    assert "35" not in mf2  # no bleed from adjacent columns


def test_two_column_table_and_br_clauses():
    html = (
        "<table>"
        "<tr><th>Standard</th><th>Value</th></tr>"
        "<tr><td>Maximum height:</td><td>35 feet for detached<br>25 feet for townhomes</td></tr>"
        "<tr><td>Rear setback</td><td>10 feet</td></tr>"
        "</table>"
    )
    text = html_to_text(html)
    # Label/value pairs, with <br> preserved as a clause separator, not a run-on.
    assert "Maximum height: 35 feet for detached ; 25 feet for townhomes" in text
    assert "Rear setback: 10 feet" in text


def test_chunk_text_emits_table_records_atomically_and_overlaps():
    record = "SF-3 — MINIMUM LOT SIZE: 5,750; MINIMUM LOT WIDTH: 50; MAXIMUM HEIGHT: 35; " + "MORE: 1; " * 12
    prose = [f"Paragraph {i}. " + "word " * 60 for i in range(14)]  # ~313 chars each
    text = "\n\n".join([record, *prose])

    chunks = chunk_text(text)

    assert chunks[0] == record  # the record is its own chunk, never merged into prose
    assert all(len(c) <= CHUNK_CHARS + CHUNK_OVERLAP for c in chunks)
    # Sliding-window overlap: consecutive prose chunks share a trailing paragraph.
    prose_chunks = chunks[1:]
    assert len(prose_chunks) >= 2
    tail_para = prose_chunks[0].split("\n\n")[-1]
    assert prose_chunks[1].startswith(tail_para)
    # Nothing lost: every paragraph appears in some chunk.
    assert all(any(p in c for c in chunks) for p in prose)


def test_extract_section_ref():
    assert extract_section_ref("§ 25-2-492 - SITE DEVELOPMENT REGULATIONS") == "§ 25-2-492"
    assert extract_section_ref("ARTICLE 5. - USE REGULATIONS") == "ARTICLE 5."
    assert extract_section_ref("General Provisions") is None


def test_freshness_label():
    banner = "<div>Codified through Ordinance No. 2025-041, adopted May 6, 2025. (Supp. No. 8)</div>"
    assert freshness_label(banner) == (
        "Code current through Supp. No. 8 (Ordinance No. 2025-041, adopted May 6, 2025)"
    )
    # Unrecognized shape stays a truthful raw label; empty banner yields none.
    assert freshness_label("Current as of last supplement") == "Current as of last supplement"
    assert freshness_label("  ") is None
