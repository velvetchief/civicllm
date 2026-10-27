"""Pure retrieval helpers (query analysis) and the LLM listwise rerank contract.
The rerank tests use a fake LLM — fused order must survive a bad or crashing
rerank model, and the fused head may never be vetoed."""

import asyncio

from app.rag.rerank import KEEP_TOP_FUSED, rerank
from app.rag.retrieve import _code_tokens, _keyword_or_query

from .conftest import make_chunk


class ScriptedLLM:
    name = "scripted"

    def __init__(self, reply: str | None):
        self.reply = reply  # None -> raise, simulating a provider outage

    async def generate(self, system: str, user: str, max_tokens: int = 1024) -> str:
        if self.reply is None:
            raise RuntimeError("provider down")
        return self.reply

    async def generate_stream(self, system: str, user: str, max_tokens: int = 1024):
        yield await self.generate(system, user, max_tokens)  # protocol completeness


def test_code_tokens_extracted_deduped_and_uppercased():
    q = "How tall can I build in sf-3 near § 25-2-492? SF-3 has limits; my APN is 1234."
    assert _code_tokens(q) == ["SF-3", "25-2-492"]
    # Prose without code-like identifiers must not fabricate an exact-match arm.
    assert _code_tokens("how tall can my house be") == []


def test_keyword_or_query_drops_stopwords_and_dedupes():
    q = "What is the maximum height for a home in an SF-3 zone? The height matters."
    out = _keyword_or_query(q)
    terms = out.split(" OR ")
    assert "height" in terms and "sf-3" in terms and "maximum" in terms
    assert terms.count("height") == 1  # deduped
    assert not {"what", "is", "the", "for", "a", "in", "an"} & set(terms)


def test_rerank_keeps_fused_head_and_appends_picks():
    chunks = [make_chunk(i, f"chunk {i}") for i in range(1, 9)]
    picked = asyncio.run(rerank(ScriptedLLM("6, 2, 5"), "q", chunks, k=5))

    ids = [c.chunk_id for c in picked]
    # Fused head is guaranteed (never vetoed), then the model's novel picks, capped at k.
    assert ids[:KEEP_TOP_FUSED] == [1, 2, 3]
    assert ids == [1, 2, 3, 6, 5]


def test_rerank_falls_back_to_fused_order_on_failure():
    chunks = [make_chunk(i, f"chunk {i}") for i in range(1, 9)]
    # Provider exception -> fused order.
    ids = [c.chunk_id for c in asyncio.run(rerank(ScriptedLLM(None), "q", chunks, k=4))]
    assert ids == [1, 2, 3, 4]
    # Out-of-range junk reply -> fused head still survives.
    ids = [c.chunk_id for c in asyncio.run(rerank(ScriptedLLM("zero 99 relevant"), "q", chunks, k=4))]
    assert ids == [1, 2, 3]
    # Fewer chunks than k -> no LLM call needed, order untouched.
    short = chunks[:3]
    assert asyncio.run(rerank(ScriptedLLM(None), "q", short, k=4)) == short
