"""Streaming must never leak the NOT_IN_CORPUS sentinel to the client, and the
pre-generation grounding floor (Guard 1) must refuse before any delta is emitted.
Retrieval and the LLM are replaced with in-memory fakes — no network, no DB."""

import asyncio

import app.rag.answer as answer_mod
from app.rag.answer import Answer, stream_answer

from .conftest import make_chunk


class FakeLLM:
    name = "fake"

    def __init__(self, fragments: list[str]):
        self.fragments = fragments

    async def generate(self, system: str, user: str, max_tokens: int = 1024) -> str:
        return "".join(self.fragments)

    async def generate_stream(self, system: str, user: str, max_tokens: int = 1024):
        for fragment in self.fragments:
            yield fragment


def _run_stream(monkeypatch, tenant, fragments, chunks):
    async def fake_retrieve(tenant_id, query, k_per_arm, k_final):
        return chunks

    monkeypatch.setattr(answer_mod, "retrieve", fake_retrieve)
    monkeypatch.setattr(answer_mod, "get_llm", lambda provider=None: FakeLLM(fragments))

    async def collect():
        return [e async for e in stream_answer(tenant, "public", "How tall in SF-3?")]

    return asyncio.run(collect())


def _split(events) -> tuple[list[str], Answer]:
    deltas = [payload for kind, payload in events if kind == "delta" and isinstance(payload, str)]
    kind, final = events[-1]
    assert kind == "final" and isinstance(final, Answer)
    return deltas, final


def test_stream_never_leaks_sentinel(monkeypatch, tenant):
    chunks = [make_chunk(1, "Maximum height is 35 feet.")]
    # Sentinel split across fragments — the holdback buffer must still catch it.
    events = _run_stream(monkeypatch, tenant, ["NOT_IN", "_CORPUS"], chunks)

    deltas, final = _split(events)
    assert deltas == []  # not a single character reached the client
    assert final.refused
    assert "NOT_IN_CORPUS" not in final.text


def test_stream_delivers_deltas_and_grounded_final(monkeypatch, tenant):
    chunks = [make_chunk(1, "In SF-3 the maximum building height is 35 feet.")]
    fragments = ["The maximum height ", "in SF-3 is ", "**35 feet** [1]."]
    events = _run_stream(monkeypatch, tenant, fragments, chunks)

    deltas, final = _split(events)
    assert "".join(deltas) == "".join(fragments)  # full text streamed, nothing lost
    assert final.grounded and not final.refused
    assert [s.number for s in final.sources] == [1]


def test_empty_retrieval_refuses_before_generation(monkeypatch, tenant):
    boom = FakeLLM([])

    async def fake_retrieve(tenant_id, query, k_per_arm, k_final):
        return []

    async def fail_stream(*a, **k):
        raise AssertionError("generation must not run when retrieval finds nothing")
        yield  # pragma: no cover

    boom.generate_stream = fail_stream
    monkeypatch.setattr(answer_mod, "retrieve", fake_retrieve)
    monkeypatch.setattr(answer_mod, "get_llm", lambda provider=None: boom)

    async def collect():
        return [e async for e in stream_answer(tenant, "public", "Anything?")]

    events = asyncio.run(collect())
    assert len(events) == 1
    deltas, final = _split(events)
    assert deltas == [] and final.refused and final.next_steps
