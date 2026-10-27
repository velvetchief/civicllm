"""LLM listwise rerank. Fusion ranking is recall-oriented; the top of the fused
list often carries topically-related-but-wrong chunks (an exception clause instead
of the base regulation). A cheap rerank pass — "which excerpts directly answer?" —
fixes precision generically, with no per-corpus tuning. Falls back to fused order
if the model's reply doesn't parse."""

import bisect
import re

from ..providers.base import LLMProvider
from .retrieve import RetrievedChunk, _code_tokens

# The reranker refines the tail; it may not veto the head. Fusion's top candidates
# have earned their rank from four independent retrieval arms — a small rerank
# model dropping them (observed with multi-entity chunks) is a worse failure mode
# than carrying a few extra excerpts.
KEEP_TOP_FUSED = 3

_SYSTEM = "You rank source excerpts by how directly they answer a question. Reply with numbers only."

_PREVIEW_CHARS = 500


def _preview(question: str, content: str) -> str:
    """Query-aware preview. A blind head-of-chunk preview hides the evidence when a
    chunk covers several entities (e.g. a section describing districts AG, RE, and
    R-1 in sequence — the R-1 table is mid-chunk). Show the window with the densest
    cluster of query terms, keeping the first line (the citation crumb) for context."""
    head, _, _body = content.partition("\n")
    lower = content.lower()

    terms = {t.lower() for t in _code_tokens(question)}
    terms |= set(re.findall(r"[a-z]{4,}", question.lower()))

    hits: list[int] = []
    for term in terms:
        start = 0
        while (i := lower.find(term, start)) != -1:
            hits.append(i)
            start = i + 1
    if not hits:
        return content[:_PREVIEW_CHARS]

    hits.sort()
    window_width = 360
    best_pos, best_count = hits[0], 0
    for idx, pos in enumerate(hits):
        count = bisect.bisect_right(hits, pos + window_width) - idx
        if count > best_count:
            best_count, best_pos = count, pos

    if best_pos < len(head) + 150:
        return content[:_PREVIEW_CHARS]
    head = head[:160]
    start = max(len(head), best_pos - 80)
    window = content[start : start + _PREVIEW_CHARS - len(head)]
    return f"{head}\n…{window}"


async def rerank(
    llm: LLMProvider, question: str, chunks: list[RetrievedChunk], k: int
) -> list[RetrievedChunk]:
    if len(chunks) <= k:
        return chunks

    listing = "\n\n".join(f"[{i}] {_preview(question, ch.content)}" for i, ch in enumerate(chunks, 1))
    user = (
        f"Question: {question}\n\nExcerpts:\n{listing}\n\n"
        f"Reply with the numbers of up to {k} excerpts that contain information "
        f"directly answering the question, most relevant first, comma-separated. "
        f"Numbers only."
    )
    try:
        out = await llm.generate(_SYSTEM, user, max_tokens=64)
    except Exception:
        return chunks[:k]

    picked = [int(n) for n in re.findall(r"\d+", out) if 1 <= int(n) <= len(chunks)]
    guaranteed = list(range(1, min(KEEP_TOP_FUSED, len(chunks)) + 1))
    final = [chunks[n - 1] for n in dict.fromkeys(guaranteed + picked)][:k]
    return final if final else chunks[:k]
