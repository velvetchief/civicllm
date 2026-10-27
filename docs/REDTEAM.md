# Red-team report — UI/UX (2026-07-05)

> **STATUS (2026-07-06): all 41 findings fixed** (3 parallel agents + integration
> pass; see docs/REDTEAM-FIXPLAN.md). Live-verified: cancel mid-stream, localized
> error cards with channel handoffs + Retry, source renumbering (retroactive on
> stored permalinks), pre-wrap answers, 125px mobile header (was 229px), sanitized
> backend errors. Bonus catch during verification: a hallucinated pseudo-sentinel
> ("NO_SE_INFORMA_SOBRE_ESTE_TEMA [1]…[8]") evaded the refusal guards — now blocked
> by an ALL-CAPS snake_case detector + regression tests. Evals: Brownsville 10/10,
> Austin 9/10 (pre-existing Q6 7B quirk, resolved on 14B).

Method: live adversarial browser session (hostile input, mid-stream sabotage, provider
misconfig, backend kill, 404s, mobile viewport, latency measurement) + independent
code-level review of every frontend file. Findings verified against running app where
marked **[live]**.

## P0 — broken

1. **Multi-paragraph answers render as a wall of text.** `.answer-text` lacks
   `white-space: pre-wrap`, so every newline the model emits collapses. Any answer
   longer than one paragraph is unreadable. (globals.css:160)

## P1 — hurts users

2. **No cancel, no post-header timeout.** The 8s abort guards only headers; a hung
   stream locks the entire app (readOnly input, disabled button) until reload. With a
   local 7B, **measured 42s** for a full answer **[live]** — and the wait copy stalls
   at stage two ("Reading the sections…") after 3s, so users stare at one line for
   40+ seconds with no elapsed signal and no way out. (sse.ts, page.tsx)
3. **Error turns dead-end.** Copy says "use the official channels below" but errors
   render zero channels — `tenant.channels` is fetched and never used **[live,
   backend-kill + Claude-no-key]**. Violates our own refusal doctrine.
4. **Raw internals shown to residents**: "Could not resolve authentication method…",
   "Failed to fetch" — verbatim, in English, inside Spanish chrome **[live]**.
5. **The trust badge fails AA.** "Grounded in cited sources" green #1f8a65 = 4.01:1
   on canvas. The product's core trust signal, illegible to low-vision users.
6. **"Copy with citations" produces orphan markers**: text keeps `[4]` but the
   Sources lines carry no numbers — the staff paste artifact doesn't map.
7. **Focus dropped after asking from an example** (block unmounts → focus to body),
   contradicting the shipped a11y claim.
8. **Toggles stay live mid-stream**: switching mode/language mid-answer flips chrome
   around an in-flight answer, forces ES→EN, and grants staff tools to resident
   answers **[live]**.
9. **No-conversation-memory is never disclosed.** The transcript looks like a chat
   and the permalink says "Ask a follow-up," but every request is context-free —
   "what about corner lots?" silently mis-answers.
10. **Staff mode + "Claude (dev)" toggle are public, unauthenticated UI** — internal
    jargon in resident chrome; a resident can route questions to Claude while the
    pitch is "private model" **[live]**. Header also costs **33% of a 360×700
    viewport** largely because of these toggles **[live]**.

## P2 — degrades the product

11. Partial streamed answer vaporized when a late error replaces it.
12. Input cleared at submit → failed question must be retyped **[live]**; no Retry.
13. Localized error copy missing (see #4); permalink 404 is English-only **[live]**.
14. Provider badge can render literal "anthropic" in resident UI.
15. Missing `answer_id` → duplicate DOM ids → citation chips jump to the wrong turn.
16. Footer "About this tool" reopens the notice off-screen (no scroll/focus); no-op if
    tenant fetch failed. Scope notice also reappears mid-conversation, shoving the
    streaming answer down **[live]**.
17. Tenant-fetch failure degrades silently (no scope, no examples, broken placeholder).
18. **Sources keep retrieval numbers** — a single source labeled "[4]" reads like
    sources 1–3 were withheld **[live]**. Renumber 1..k client-side.
19. Long unbroken word/URL overflows `.q` horizontally at 360px **[live]**.
20. `[n]` inside `**bold**` never becomes a citation chip.
21. Unguarded localStorage throws in sandboxed iframes (our own embed roadmap).
22. Permalink never shows its answer date (`answeredOn` is dead code) — stale-answer
    trust gap as the code moves supplement to supplement.
23. ES copy: "Respuestas verificadas" overclaims; tú/usted register mixed;
    "Prueba preguntar" unidiomatic.
24. Touch targets: cite chips ≈26px, related chips ≈29px — fails the 44px claim on
    the exact affordance the doctrine calls key.
25. Language toggle rewrites history chrome (EN answers under "Preguntaste:") and
    mislabels `lang` for screen readers; store language per turn.
26. Staff-mode permalinks render staff tools to any anonymous visitor.

## P3 — polish/robustness

27. Stream body never `cancel()`ed on early return/error (connection held open).
28. One malformed SSE frame discards an already-streamed answer.
29. Double-submit guard relies on React flush timing; use a ref.
30. `<html lang>`/`<title>` never localized; permalinks share one generic title.
31. Accent #d04200 is 4.39:1 on canvas (below AA) — fine on white cards, don't use it
    for text on canvas/refusal surfaces.
32. Busy "…" button state at 2.1:1 conveys state via an illegible control.
33. Double disclosure marker in older Safari (missing `::-webkit-details-marker`).
34. `Source.excerpt` shipped in every payload, rendered nowhere.
35. legacyCopy fallback dumps focus to body.
36. Permalink page has no aria-live for its loading/notfound transitions.
37. `role="search"` mislabels the composer.
38. Streaming shows literal `**` until the closing marker arrives (visible flicker on
    every bolded figure).
39. `href`s from the API rendered without scheme check — allow http(s) only.
40. Citation flash timers stack across rapid clicks.
41. Ask-input placeholder truncates ("…Unified Developm") — write a short one **[live]**.

## What held up under attack **[live]**

- XSS: `<script>` injection renders inert as literal text.
- Garbage-wrapped questions still retrieve and answer correctly (35 feet, cited).
- Permalink 404 is graceful (message + route home).
- No scroll hijack during streaming; new-turn-only autoscroll behaves.
- Double-submit is effectively blocked (readOnly input + disabled button + guard).

## Recommended fix order

1. P0 #1 + the wait/cancel cluster (#2) — these define the felt experience.
2. Error-path cluster (#3, #4, #12, #13) — one workstream: localized error copy,
   channels on every dead end, Retry button, keep partials.
3. Trust/a11y cluster (#5, #7, #18, #24, #31) — contrast, focus, renumbering, targets.
4. Resident-surface hygiene (#10 provider/staff gating, header slimming, #9 wording).
5. Everything else in listed order.
