"""The golden-set grader decides every published eval score, so its rules are pinned
here: figures must appear, the governing section must be cited (any-of for a list),
out-of-corpus questions must be refused, and the saved record keeps the full answer."""

import json

from app.rag.answer import Answer, Source
from eval.run_eval import case_record, check


def _answer(
    text="Max height is 35 feet [1].", *, refused=False, grounded=True, refs=("§ 25-2-492",)
):
    sources = [
        Source(
            number=i,
            title="Site Development Regulations",
            hierarchy=[],
            section_ref=ref,
            source_url="https://example.test",
            excerpt="",
            quote="",
        )
        for i, ref in enumerate(refs, 1)
    ]
    return Answer(
        text=text,
        grounded=grounded,
        sources=sources,
        disclaimer="",
        provider="ollama",
        refused=refused,
    )


def test_correct_cited_answer_passes():
    case = {"question": "q", "must_contain": ["35 feet"], "must_cite": "25-2-492"}
    assert check(case, _answer()) == (True, [])


def test_missing_figure_and_wrong_citation_both_reported():
    case = {"question": "q", "must_contain": ["40 feet"], "must_cite": "25-2-999"}
    ok, reasons = check(case, _answer())
    assert not ok
    assert len(reasons) == 2


def test_must_cite_list_is_any_of():
    case = {"question": "q", "must_cite": ["25-2-999", "25-2-492"]}
    assert check(case, _answer())[0]


def test_ungrounded_answer_fails():
    ok, reasons = check({"question": "q"}, _answer(grounded=False))
    assert not ok and "not grounded" in reasons[0]


def test_refusal_cases():
    out_of_corpus = {"question": "q", "expect_refusal": True}
    assert check(out_of_corpus, _answer(refused=True))[0]
    assert not check(out_of_corpus, _answer())[0]
    assert not check({"question": "q"}, _answer(refused=True))[0]


def test_case_record_keeps_full_answer_and_is_json_safe():
    text = "Max height is 35 feet [1]. " * 20
    case = {"question": "How tall?", "must_contain": ["35 feet"], "must_cite": "25-2-492"}
    record = case_record(3, case, _answer(text), True, [])
    assert record["answer"] == text
    assert record["sources"] == [
        {"number": 1, "section_ref": "§ 25-2-492", "title": "Site Development Regulations"}
    ]
    assert record["language"] == "en" and record["expect_refusal"] is False
    json.dumps(record)
