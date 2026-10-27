"""Golden-set eval: every answer must (a) contain the known-correct figure,
(b) cite the governing section, and (c) refuse cleanly on out-of-corpus questions.

Usage:  uv run python -m eval.run_eval [tenant] [provider]
        uv run python -m eval.run_eval austin ollama
        uv run python -m eval.run_eval austin --retrieval   # retrieval-only check
"""

import asyncio
import json
import sys
from pathlib import Path

from app.config import settings
from app.db import init_db
from app.rag.answer import answer_question
from app.rag.retrieve import retrieve
from app.tenant import load_tenant


async def run(tenant_id: str, provider: str | None) -> int:
    init_db()
    tenant = load_tenant(tenant_id)
    golden = Path(__file__).parent / f"golden_{tenant_id}.jsonl"
    cases = [json.loads(line) for line in golden.read_text().splitlines() if line.strip()]

    passed = 0
    for i, case in enumerate(cases, 1):
        result = await answer_question(
            tenant,
            case.get("mode", "public"),
            case["question"],
            provider,
            language=case.get("language", "en"),
        )
        ok, reasons = check(case, result)
        passed += ok
        status = "PASS" if ok else "FAIL"
        print(f"[{i:02d}] {status}  {case['question'][:70]}")
        if not ok:
            for r in reasons:
                print(f"      - {r}")
            print(f"      answer: {result.text[:200]}")

    print(f"\n{passed}/{len(cases)} passed  (provider={provider or 'default'})")
    return 0 if passed == len(cases) else 1


def check(case: dict, result) -> tuple[bool, list[str]]:
    reasons = []
    if case.get("expect_refusal"):
        if not result.refused:
            reasons.append("expected refusal, got an answer")
        return (not reasons), reasons

    if result.refused:
        reasons.append("unexpected refusal")
    for needle in case.get("must_contain", []):
        if needle not in result.text:
            reasons.append(f"missing expected figure: {needle!r}")
    cite = case.get("must_cite")
    if cite:
        accepted = cite if isinstance(cite, list) else [cite]  # any-of when a list
        cited = any(
            c in (s.section_ref or "") or c in (s.title or "")
            for c in accepted
            for s in result.sources
        )
        if not cited:
            reasons.append(f"no cited source matching {accepted!r}")
    if not result.grounded:
        reasons.append("answer not grounded (no valid citations)")
    return (not reasons), reasons


async def run_retrieval_only(tenant_id: str) -> int:
    """Do the top-k chunks contain the expected figure + section? Isolates
    retrieval quality from generation quality."""
    init_db()
    golden = Path(__file__).parent / f"golden_{tenant_id}.jsonl"
    cases = [json.loads(line) for line in golden.read_text().splitlines() if line.strip()]
    passed = 0
    for i, case in enumerate(cases, 1):
        if case.get("expect_refusal"):
            continue
        # Measure the pre-rerank candidate window — what the reranker gets to see.
        chunks = await retrieve(
            tenant_id, case["question"], settings.retrieve_k_per_arm, settings.rerank_candidates
        )
        figures_ok = all(
            any(fig in ch.content for ch in chunks) for fig in case.get("must_contain", [])
        )
        cite = case.get("must_cite", "")
        accepted = cite if isinstance(cite, list) else [cite] if cite else []
        cite_ok = not accepted or any(
            c in (ch.section_ref or "") or c in (ch.title or "")
            for c in accepted
            for ch in chunks
        )
        hit_rank = next(
            (
                r
                for r, ch in enumerate(chunks, 1)
                if any(c in (ch.section_ref or "") or c in (ch.title or "") for c in accepted)
                and all(f in ch.content for f in case.get("must_contain", []))
            ),
            None,
        )
        ok = figures_ok and cite_ok
        passed += ok
        print(
            f"[{i:02d}] {'PASS' if ok else 'FAIL'}  answer-chunk rank: {hit_rank}  "
            f"{case['question'][:60]}"
        )
    total = sum(1 for c in cases if not c.get("expect_refusal"))
    print(f"\nretrieval: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    tenant_arg = sys.argv[1] if len(sys.argv) > 1 else "austin"
    if "--retrieval" in sys.argv:
        raise SystemExit(asyncio.run(run_retrieval_only(tenant_arg)))
    provider_arg = sys.argv[2] if len(sys.argv) > 2 else None
    raise SystemExit(asyncio.run(run(tenant_arg, provider_arg)))
