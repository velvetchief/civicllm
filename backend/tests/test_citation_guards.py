"""The product promise: every answer is grounded in cited sections, and anything
the corpus doesn't cover is an honest, routed refusal. These tests exercise the
post-generation guards in app.rag.answer._finalize — citation extraction, refusal
detection (sentinel + soft declines in both languages), the numeric-overlap
grounding fallback, and source-card assembly."""

from app.rag.answer import QUOTE_CHARS, _finalize
from app.rag.prompts import REFUSAL_SENTINEL

from .conftest import make_chunk


def _three_chunks():
    return [
        make_chunk(11, "In SF-3, the maximum building height is 35 feet.", section_ref="§ 25-2-492"),
        make_chunk(12, "Minimum lot size in SF-3 is 5,750 square feet.", section_ref="§ 25-2-492"),
        make_chunk(13, "A rear setback of 10 feet applies to detached houses.", section_ref="§ 25-2-493"),
    ]


def test_cited_answer_builds_matching_sources(tenant):
    raw = "The maximum height is **35 feet** [1]. A rear setback of 10 feet applies [3]."
    answer = _finalize(tenant, "public", raw, _three_chunks(), "ollama", "en")

    assert answer.grounded and not answer.refused
    assert answer.text == raw
    # Only the cited chunks become sources, numbered to match the bracket markers.
    assert [s.number for s in answer.sources] == [1, 3]
    assert answer.sources[0].section_ref == "§ 25-2-492"
    assert answer.sources[1].section_ref == "§ 25-2-493"
    assert "35 feet" in answer.sources[0].quote
    # Public answers always carry the handoff card.
    assert answer.next_steps and answer.next_steps[0].label == "Call Development Services"


def test_sentinel_refusal_routes_to_channels(tenant):
    answer = _finalize(tenant, "public", REFUSAL_SENTINEL, _three_chunks(), "ollama", "en")

    assert answer.refused
    assert answer.grounded  # an honest refusal is a grounded outcome
    assert answer.sources == []
    assert REFUSAL_SENTINEL not in answer.text  # the sentinel never reaches users
    assert "Testville Land Development Code" in answer.text
    assert answer.next_steps[0].url == "https://example.test/contact"


def test_soft_decline_without_sentinel_is_a_refusal(tenant):
    # Smaller local models often decline politely instead of emitting the sentinel.
    raw = "The provided excerpts do not contain information about food truck permits."
    answer = _finalize(tenant, "public", raw, _three_chunks(), "ollama", "en")

    assert answer.refused
    assert "excerpts do not contain" not in answer.text  # replaced by the refusal template


def test_spanish_soft_decline_and_localized_refusal(tenant):
    raw = "Lo siento, pero los extractos proporcionados no contienen esa información."
    answer = _finalize(tenant, "public", raw, _three_chunks(), "ollama", "es")

    assert answer.refused
    assert answer.text.startswith("No encontré esto en")
    assert answer.disclaimer == "No es asesoría legal."
    assert answer.next_steps[0].label == "Llame a Servicios de Desarrollo"


def test_uncited_answer_grounded_by_numeric_overlap(tenant):
    # No bracket markers, and an out-of-range [7] must be ignored — but the figure
    # 5,750 literally appears in chunk 2, so verify-the-content grounds the answer
    # and promotes that chunk to a cited source.
    raw = "The minimum lot size is **5,750 square feet** [7]."
    answer = _finalize(tenant, "public", raw, _three_chunks(), "ollama", "en")

    assert answer.grounded and not answer.refused
    assert [s.number for s in answer.sources] == [2]
    assert "5,750" in answer.sources[0].quote


def test_unverifiable_uncited_answer_is_not_grounded(tenant):
    # "2 permits" appears in no chunk, and bare list-marker numbers (1, 2, 3) must
    # not count as corroborating figures.
    raw = "You need 2 permits. 1. Apply. 2. Wait. 3. Build."
    answer = _finalize(tenant, "public", raw, _three_chunks(), "ollama", "en")

    assert not answer.refused
    assert not answer.grounded
    assert answer.sources == []


def test_related_rules_deduped_by_document_and_capped(tenant):
    chunks = [
        make_chunk(1, "Maximum height is 35 feet.", document_id=100, title="Heights"),
        make_chunk(2, "More height details.", document_id=100, title="Heights"),  # same doc as cited
        make_chunk(3, "Setbacks are 10 feet.", document_id=200, title="Setbacks"),
        make_chunk(4, "Setback exceptions.", document_id=200, title="Setbacks"),  # dup of 3
        make_chunk(5, "Impervious cover limits.", document_id=300, title="Cover"),
        make_chunk(6, "Parking minimums.", document_id=400, title="Parking"),
        make_chunk(7, "Tree preservation.", document_id=500, title="Trees"),
    ]
    answer = _finalize(tenant, "staff", "Height is **35 feet** [1].", chunks, "ollama", "en")

    assert [s.number for s in answer.sources] == [1]
    titles = [r.title for r in answer.related]
    assert titles == ["Setbacks", "Cover", "Parking"]  # cited doc + dups excluded, capped at 3
    assert answer.next_steps == []  # staff mode: handoff card only on refusal


def test_source_excerpt_and_quote_are_capped(tenant):
    long_content = "The maximum height is 35 feet. " + "x" * 3000
    answer = _finalize(tenant, "staff", "Height is 35 feet [1].", [make_chunk(1, long_content)], "ollama", "en")

    src = answer.sources[0]
    assert len(src.excerpt) == 301 and src.excerpt.endswith("…")
    assert len(src.quote) == QUOTE_CHARS + 1 and src.quote.endswith("…")


def test_pseudo_sentinel_with_valid_citations_is_a_refusal(tenant):
    """Observed live (red team, 2026-07-06): the model invented a Spanish sentinel
    and cited every excerpt — valid [n] markers must not launder a refusal into a
    'grounded' answer."""
    raw = "NO_SE_INFORMA_SOBRE_ESTE_TEMA [1][2][3]."
    answer = _finalize(tenant, "public", raw, _three_chunks(), "ollama", "es")

    assert answer.refused
    assert answer.sources == []
    assert "NO_SE_INFORMA" not in answer.text


def test_english_pseudo_sentinel_variant_is_a_refusal(tenant):
    raw = "NOT_COVERED_BY_SOURCES"
    answer = _finalize(tenant, "public", raw, _three_chunks(), "ollama", "en")

    assert answer.refused
