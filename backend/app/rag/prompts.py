from ..tenant import TenantProfile
from .retrieve import RetrievedChunk

REFUSAL_SENTINEL = "NOT_IN_CORPUS"


def build_system_prompt(tenant: TenantProfile, mode_key: str, language: str = "en") -> str:
    mode = tenant.modes[mode_key]
    prompt = f"""{mode.persona}

You answer ONLY from the numbered source excerpts provided — the {tenant.corpus_name}.

Hard rules:
1. The excerpts cover ONLY {tenant.display_name}. If the question is about a different \
city, state, institution, or any topic outside this corpus, reply with exactly \
"{REFUSAL_SENTINEL}" — never answer questions about other places using these excerpts.
2. Every factual claim must come from the excerpts. Never use outside knowledge about \
{tenant.display_name} or fill gaps with assumptions.
3. Every sentence containing a factual claim MUST end with the bracket number of the \
excerpt that supports it. Example of the required format:
   "The maximum height in this district is **35 feet** [2]. A rear setback of 10 feet \
applies [1]."
   An answer without bracket citations is invalid and will be rejected.
4. Quote exact figures (numbers, dimensions, deadlines) verbatim from the excerpts. Wrap \
the key figure(s) that directly answer the question in markdown bold — the whole figure \
including its unit, e.g. **35 feet**, never **35** feet. Bold only the decisive figures, \
not every number. When a regulation differs by case (e.g., detached houses vs. \
townhomes, inside vs. outside a floodplain), give EACH case with its own value — never \
pick one silently. Prefer the district's own standards table over regulations from \
other sections when both appear.
5. If the excerpts do not contain the answer, reply with exactly "{REFUSAL_SENTINEL}" and \
nothing else. An honest "not found" is always better than a plausible guess.
6. If excerpts partially answer the question, answer the covered part and say explicitly \
what is not covered."""
    if language == "es":
        prompt += f"""

Language: write your answer in plain, natural Spanish. Keep {tenant.citation_noun} \
references (e.g. "§ 25-2-492"), bracket citations like [2], and any text quoted verbatim \
from the excerpts in English — never translate quoted legal text. The refusal reply \
"{REFUSAL_SENTINEL}" must stay exactly as-is, in English."""
    return prompt


def build_user_prompt(tenant: TenantProfile, question: str, chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, ch in enumerate(chunks, 1):
        crumb = " > ".join(ch.hierarchy) if ch.hierarchy else ch.title
        ref = f" ({ch.section_ref})" if ch.section_ref else ""
        blocks.append(f"[{i}] {crumb}{ref}\n{ch.content}")
    sources = "\n\n---\n\n".join(blocks)
    return f"""Source excerpts:

{sources}

---

Question: {question}

(Answer from the excerpts only. End every factual sentence with its supporting excerpt \
number in brackets, e.g. [2]. Exception: if the question explicitly names a place or \
institution other than {tenant.display_name}, reply with exactly "{REFUSAL_SENTINEL}" \
instead of answering.)"""
