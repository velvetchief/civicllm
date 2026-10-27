import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from ..config import settings
from ..providers import get_llm
from ..providers.base import LLMProvider
from ..tenant import TenantProfile
from .prompts import REFUSAL_SENTINEL, build_system_prompt, build_user_prompt
from .rerank import rerank
from .retrieve import RetrievedChunk, retrieve

QUOTE_CHARS = 2000  # cap on the inline-verification quote per source
# Streaming: hold back the first characters so the refusal sentinel (or its prefix)
# never reaches the client as a delta.
STREAM_HOLDBACK = 30


@dataclass
class Source:
    number: int
    title: str
    hierarchy: list[str]
    section_ref: str | None
    source_url: str | None
    excerpt: str
    quote: str  # full chunk text (capped) — verification lives *in* the answer


@dataclass
class Related:
    """A non-cited rerank candidate: 'related rules that often apply'."""

    title: str
    section_ref: str | None
    source_url: str | None


@dataclass
class NextStep:
    """A real handoff channel — refusals route, never dead-end."""

    label: str
    detail: str
    url: str | None


@dataclass
class Answer:
    text: str
    grounded: bool
    sources: list[Source]
    disclaimer: str
    provider: str
    refused: bool = False
    answer_id: str = ""  # assigned when the answer is persisted
    related: list[Related] = field(default_factory=list)
    next_steps: list[NextStep] = field(default_factory=list)


# Smaller models sometimes invent their own sentinel instead of emitting
# NOT_IN_CORPUS verbatim (observed live: "NO_SE_INFORMA_SOBRE_ESTE_TEMA [1]…[8]").
# Any ALL-CAPS snake_case token is a refusal signal, whatever the language —
# real answers never contain one.
_PSEUDO_SENTINEL = re.compile(r"\b[A-ZÁÉÍÓÚÜÑ]{2,}(?:_[A-ZÁÉÍÓÚÜÑ0-9]{2,})+\b")

_SOFT_REFUSAL = re.compile(
    r"(excerpts|sources|information provided|provided (?:excerpts|information|sources|"
    r"ordinances?|zoning information))\s+(?:do(?:es)? not|don't|doesn't|cannot|can't)"
    r"|not (?:directly )?addressed in the provided"
    r"|cannot (?:provide|answer|determine)[^.]{0,60}based on the (?:given|provided)"
    # Spanish variants: smaller models sometimes decline politely in the answer
    # language instead of emitting the sentinel.
    r"|(?:extractos|fragmentos|fuentes)(?:\s+\S+){0,3}\s+no\s+(?:contienen|incluyen|cubren)"
    r"|no (?:se encuentra|aparece|está cubiert[oa]) en (?:los|las) (?:extractos|fuentes)",
    re.IGNORECASE,
)

_REFUSAL_TEXT_EN = (
    "I couldn't find this in the {corpus}. Rather than guess, "
    "I'm telling you it isn't covered by the sources I can search. "
    "Try rephrasing, or consult {display} directly."
)
_REFUSAL_TEXT_ES = (
    "No encontré esto en {corpus}. En lugar de adivinar, "
    "le digo que las fuentes que puedo consultar no lo cubren. "
    "Intente reformular la pregunta o comuníquese directamente con {display}."
)


def _cited_numbers(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"\[(\d+)\]", text)}


def _next_steps(tenant: TenantProfile, language: str) -> list[NextStep]:
    if language == "es":
        return [
            NextStep(label=c.label_es or c.label, detail=c.detail_es or c.detail, url=c.url)
            for c in tenant.channels
        ]
    return [NextStep(label=c.label, detail=c.detail, url=c.url) for c in tenant.channels]


def _refusal(
    tenant: TenantProfile, disclaimer: str, provider_name: str, language: str
) -> Answer:
    template = _REFUSAL_TEXT_ES if language == "es" else _REFUSAL_TEXT_EN
    return Answer(
        text=template.format(corpus=tenant.corpus_name, display=tenant.display_name),
        grounded=True,  # an honest refusal is a grounded outcome
        sources=[],
        disclaimer=disclaimer,
        provider=provider_name,
        refused=True,
        next_steps=_next_steps(tenant, language),  # refusals hand off, never dead-end
    )


_TRANSLATE_SYSTEM = (
    "You translate questions into English for searching an English-language legal code. "
    "Reply with ONLY the English translation — no quotes, no commentary. Keep code-like "
    "identifiers (e.g. SF-3, § 25-2-492) exactly as written."
)


async def _search_query(llm: LLMProvider, question: str, language: str) -> str:
    """Cross-lingual retrieval: the corpus is English, so a non-English question is
    translated for retrieval + rerank only. Generation still sees the original
    (and answers in the user's language per the system prompt)."""
    if language == "en":
        return question
    try:
        translated = (await llm.generate(_TRANSLATE_SYSTEM, question, max_tokens=120)).strip()
        return translated or question
    except Exception:
        return question


async def _prepare(
    tenant: TenantProfile, mode_key: str, question: str, llm: LLMProvider, language: str
) -> tuple[list[RetrievedChunk], Answer | None]:
    """Retrieve + rerank. Returns (chunks, refusal): refusal is set when nothing
    relevant was retrieved (Guard 1 — refuse before generation)."""
    search_query = await _search_query(llm, question, language)
    candidates = await retrieve(
        tenant.id, search_query, settings.retrieve_k_per_arm, settings.rerank_candidates
    )
    if not candidates or candidates[0].score < settings.min_grounding_score:
        disclaimer = tenant.modes[mode_key].disclaimer_for(language)
        return [], _refusal(tenant, disclaimer, llm.name, language)
    chunks = await rerank(llm, search_query, candidates, settings.retrieve_k_final)
    return chunks, None


def _finalize(
    tenant: TenantProfile,
    mode_key: str,
    raw: str,
    chunks: list[RetrievedChunk],
    provider_name: str,
    language: str,
) -> Answer:
    """Guards 2+3 over the complete generated text, then Answer assembly."""
    disclaimer = tenant.modes[mode_key].disclaimer_for(language)

    # Guard 2: model says the corpus doesn't cover it — via the sentinel, or via a
    # polite decline (smaller models often say "the excerpts do not contain…"
    # instead of emitting the sentinel). Both are refusals, not answers.
    if (
        re.search(REFUSAL_SENTINEL, raw, re.IGNORECASE)
        or _PSEUDO_SENTINEL.search(raw)
        or _SOFT_REFUSAL.search(raw)
    ):
        return _refusal(tenant, disclaimer, provider_name, language)

    # Guard 3: answer must cite. If the model skipped bracket markers (smaller local
    # models sometimes do despite instruction), fall back to verification: the
    # answer's figures must literally appear in retrieved chunks, which then become
    # the cited sources. Verify-the-content beats trust-the-model's-brackets.
    cited = _cited_numbers(raw)
    valid_cited = {n for n in cited if 1 <= n <= len(chunks)}
    if not valid_cited:
        valid_cited = _verify_by_overlap(raw, chunks)
    grounded = bool(valid_cited)

    sources = [_to_source(i, ch) for i, ch in enumerate(chunks, 1) if i in valid_cited]
    return Answer(
        text=raw,
        grounded=grounded,
        sources=sources,
        disclaimer=disclaimer,
        provider=provider_name,
        related=_related(chunks, valid_cited),
        # Public answers always carry the handoff card; staff only see it on refusal.
        next_steps=_next_steps(tenant, language) if mode_key == "public" else [],
    )


async def answer_question(
    tenant: TenantProfile,
    mode_key: str,
    question: str,
    provider: str | None = None,
    language: str = "en",
) -> Answer:
    llm = get_llm(provider)
    chunks, refusal = await _prepare(tenant, mode_key, question, llm, language)
    if refusal is not None:
        return refusal

    system = build_system_prompt(tenant, mode_key, language)
    user = build_user_prompt(tenant, question, chunks)
    raw = (await llm.generate(system, user)).strip()
    return _finalize(tenant, mode_key, raw, chunks, llm.name, language)


async def stream_answer(
    tenant: TenantProfile,
    mode_key: str,
    question: str,
    provider: str | None = None,
    language: str = "en",
) -> AsyncIterator[tuple[str, str | Answer]]:
    """Streaming variant: yields ("delta", text_fragment)… then ("final", Answer).

    Retrieval + rerank run silently first (no deltas). Generation streams, but the
    first STREAM_HOLDBACK characters are buffered so the NOT_IN_CORPUS sentinel never
    reaches the client; guards run on the complete text before "final". If the full
    text turns out to be a refusal, "final" carries the refusal answer and the
    frontend replaces any streamed text.
    """
    llm = get_llm(provider)
    chunks, refusal = await _prepare(tenant, mode_key, question, llm, language)
    if refusal is not None:
        yield ("final", refusal)
        return

    system = build_system_prompt(tenant, mode_key, language)
    user = build_user_prompt(tenant, question, chunks)

    parts: list[str] = []
    held = ""
    holding = True  # still buffering the head of the stream
    suppress = False  # sentinel spotted — emit no deltas at all
    async for fragment in llm.generate_stream(system, user):
        parts.append(fragment)
        if suppress:
            continue
        if holding:
            held += fragment
            if REFUSAL_SENTINEL in held.upper():
                suppress = True
            elif len(held) >= STREAM_HOLDBACK:
                holding = False
                yield ("delta", held)
        else:
            yield ("delta", fragment)

    raw = "".join(parts).strip()
    answer = _finalize(tenant, mode_key, raw, chunks, llm.name, language)
    if holding and not suppress and held and not answer.refused:
        yield ("delta", held)  # short answer that never reached the holdback threshold
    yield ("final", answer)


def _verify_by_overlap(answer_text: str, chunks: list[RetrievedChunk]) -> set[int]:
    """Deterministic grounding check: which chunks contain the numeric figures the
    answer asserts? Returns their 1-based indices (max 3, best-retrieved first)."""
    figures = set(re.findall(r"\d[\d,]*(?:\.\d+)?", answer_text))
    figures -= {str(n) for n in range(1, len(chunks) + 1)}  # ignore list markers
    if not figures:
        return set()
    supported = [
        i for i, ch in enumerate(chunks, 1) if any(fig in ch.content for fig in figures)
    ]
    return set(supported[:3])


def _related(chunks: list[RetrievedChunk], valid_cited: set[int]) -> list[Related]:
    """Top rerank candidates that were NOT cited — 'related rules that often apply'.
    Deduped by document (and excluding documents already cited)."""
    seen_docs = {chunks[i - 1].document_id for i in valid_cited}
    related: list[Related] = []
    for i, ch in enumerate(chunks, 1):
        if i in valid_cited or ch.document_id in seen_docs:
            continue
        seen_docs.add(ch.document_id)
        related.append(Related(title=ch.title, section_ref=ch.section_ref, source_url=ch.source_url))
        if len(related) == 3:
            break
    return related


def _to_source(number: int, ch: RetrievedChunk) -> Source:
    excerpt = ch.content[:300] + ("…" if len(ch.content) > 300 else "")
    quote = ch.content[:QUOTE_CHARS] + ("…" if len(ch.content) > QUOTE_CHARS else "")
    return Source(
        number=number,
        title=ch.title,
        hierarchy=ch.hierarchy,
        section_ref=ch.section_ref,
        source_url=ch.source_url,
        excerpt=excerpt,
        quote=quote,
    )
