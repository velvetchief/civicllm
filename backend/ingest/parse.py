"""HTML -> retrieval-ready text.

The hard part of legal/policy corpora is tables: Austin's § 25-2-492 site development
regulations is one giant matrix (rows = regulations, columns = zoning districts).
Naive tag-stripping destroys the row/column relationships the answers depend on, so
tables are linearized into "Header: value" pairs per row.
"""

import re

from bs4 import BeautifulSoup, Tag


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    for table in soup.find_all("table"):
        if isinstance(table, Tag):
            table.replace_with(_linearize_table(table))

    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t \xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _linearize_table(table: Tag) -> str:
    # A <br> inside a cell separates distinct clauses ("35 feet for detached
    # residential<br>25 feet for townhomes") — collapsing it to a space produces a
    # run-on that misleads both retrieval and generation.
    for br in table.find_all("br"):
        br.replace_with("; ")

    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        if not isinstance(tr, Tag):
            continue
        cells = []
        for td in tr.find_all(["td", "th"]):
            if not isinstance(td, Tag):
                continue
            cell = re.sub(r"\s+", " ", td.get_text(separator=" ")).strip().rstrip(":")
            # Repeat cells across their colspan so columns stay aligned with headers.
            colspan = td.get("colspan")
            span = int(colspan) if isinstance(colspan, str) and colspan.isdigit() else 1
            cells.extend([cell] * span)
        if any(cells):
            rows.append(cells)

    if len(rows) < 2:
        return " ".join(" ".join(r) for r in rows)

    headers = rows[0]

    # Two-column tables are label/value pairs (e.g. Brownsville's per-district
    # standards) — a "header" prefix on every value is noise, not signal.
    if max(len(r) for r in rows) <= 2:
        lines = []
        for row in rows:
            label = row[0] if row else ""
            value = row[1] if len(row) > 1 else ""
            if label and value and label != value:
                lines.append(f"{label}: {value}")
            elif label or value:
                lines.append(label or value)
        return "\n".join(lines)

    # Wide matrices (e.g. regulations × zoning districts) are linearized
    # column-wise ONLY: one self-contained record per column ("SF-3 — MINIMUM LOT
    # SIZE: 5,750; …; MAXIMUM HEIGHT: 35"). Row-wise renderings of a 38-column
    # table are walls of numbers that rank poorly in retrieval AND mislead the
    # generator into reading adjacent columns' values.
    if len(headers) >= 6:
        lines = []
        for i, header in enumerate(headers[1:], start=1):
            if not header:
                continue
            pairs = []
            for row in rows[1:]:
                label = row[0] if row else ""
                cell = row[i] if i < len(row) else ""
                if label and cell:
                    pairs.append(f"{label}: {cell}")
            if pairs:
                # Blank lines make each record its own paragraph for the chunker.
                lines.append(f"{header} — " + "; ".join(pairs))
        return "\n\n".join(lines)

    lines = []
    for row in rows[1:]:
        label = row[0] if row else ""
        pairs = []
        for i, cell in enumerate(row[1:], start=1):
            if not cell:
                continue
            header = headers[i] if i < len(headers) else f"col{i}"
            pairs.append(f"{header}: {cell}")
        lines.append(f"{label} — " + "; ".join(pairs) if pairs else label)
    return "\n".join(lines)


_SECTION_REF = re.compile(r"§\s*[\w.-]+|^(ARTICLE|DIVISION|CHAPTER|TITLE)\s+[\w.-]+", re.I)


def extract_section_ref(title: str) -> str | None:
    m = _SECTION_REF.search(title)
    return m.group(0).strip() if m else None
