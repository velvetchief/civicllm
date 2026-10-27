# Red-team fix plan — ownership + shared interfaces

Fixes all findings in docs/REDTEAM.md. Three agents with EXCLUSIVE file territories.
Shared contract (already landed, do not modify): lib/i18n.ts (all new keys),
lib/types.ts (Channel + channelToStep), lib/config.ts (SHOW_DEV_CONTROLS,
storageGet/storageSet), backend error sanitization (SSE error → {code}).

## Interfaces between agents (bindings — follow exactly)

1. `streamChat(body, handlers, opts?: { signal?: AbortSignal; idleTimeoutMs?: number })`
   — implemented in lib/sse.ts (Agent C), consumed by page.tsx (Agent A).
   Abort → rejects with DOMException AbortError. Default idle timeout 90_000ms
   between SSE events → rejects Error("stream_idle").
2. `components/ChannelList.tsx` (Agent B):
   `export function ChannelList({ channels, lang, heading, prominent }: { channels: Channel[]; lang: Lang; heading: string; prominent?: boolean })`
   renders `<section class="steps{ prominent}"><h3>{heading}</h3><ul>…` using
   channelToStep. Consumed by page.tsx (error turns) and AnswerView (next_steps stays
   as-is — it already receives localized steps from the API).
3. `renderAnswerText(text, sources, opts)` (Agent B) gains
   `numberMap?: Map<number, number>` (retrieval# → display#): chips render the
   display number and aria-label uses it; unmatched [n] stays literal.
4. New CSS classes (Agent C defines; A/B consume): `.cancel-btn`, `.retry-btn`,
   `.badge.incomplete`, `.notice-warn` (tenant-load warning bar).
5. Turn-local state (Agent A only): each turn snapshots `{ lang, mode }` at ask time;
   render turn chrome + lang attributes + staffTools from the snapshot, not live state.

## Agent A — app/page.tsx, app/layout.tsx ONLY

Findings: 2 (cancel button while busy; AbortController wired to streamChat; on
cancel: mark turn canceled, announce, re-enable input), 3 (error turns render
<ChannelList prominent> when tenant.channels present), 7 (after ask() from examples,
move focus to the ask input), 8+25 (snapshot lang/mode per turn; disable toggles
while busy with aria-disabled + tooltip-free), 9 (scope notice appends t.scopeStateless;
placeholder = t.askPlaceholder), 10 (provider seg rendered only when SHOW_DEV_CONTROLS
&& mode==="staff"), 11 (error after deltas keeps partial text rendered + `.badge.incomplete`),
12 (error turns get `.retry-btn` → re-ask(turn.question) with the turn's snapshot),
13 (never render raw error text: all errors → t.errorFriendly + t.errorRetryHint;
console.error the detail; backend now sends {code} not message), 16 (About link
scrolls to + focuses the scope notice; t.scopeFallback when tenant scope missing),
17 (tenant fetch: one retry after 2s; on final failure show `.notice-warn`
t.tenantLoadFailed), 21 (use storageGet/storageSet), 29 (in-flight useRef guard),
30 (useEffect: document.documentElement.lang = lang), 37 (drop role="search"),
wait stages: 0s searching / 3s reading / 12s stillWorking / 30s almostThere,
cancel affordance visible from first stage.

## Agent B — components/AnswerView.tsx, components/ChannelList.tsx (new),
## app/a/[id]/page.tsx, lib/markdownLite.tsx ONLY

Findings: 6 (citationText: text keeps [n]; Sources lines prefixed `[n] ` using
DISPLAY numbers), 14 (badge uses t.providerName(a.provider)), 15 (prefix falls back
to React useId, never "ans-local"), 18 (renumber: sources sorted by retrieval number
→ display 1..k; build numberMap for renderAnswerText; cards show display number,
sourceAria uses display), 20 (tokenize [n] inside **bold** spans), 22 (permalink
renders t.answeredOn(Intl.DateTimeFormat(lang==='es'?'es-MX':'en-US',{dateStyle:'long'})
.format(new Date(record.created_at)))), 26 (permalink NEVER renders staff tools —
viewer identity unknown), 35 (legacyCopy restores focus to the button), 36 (permalink
page gets its own visually-hidden aria-live status), 38 (unclosed ** at end of text
renders as bold-in-progress, no literal asterisks), 39 (safeHref(): only http/https
hrefs rendered; else render as plain text span), 40 (flash timeout stored per-element
via dataset/id and cleared before re-adding).

## Agent C — lib/sse.ts, app/globals.css ONLY

sse.ts: interface binding #1; 27 (reader.cancel() / res.body cancel in finally);
28 (malformed delta frame → skip + console.warn; malformed final → throw).
globals.css: 1 (.answer-text { white-space: pre-wrap; overflow-wrap: anywhere }),
5 (--success → #146c4e), 19 (.q { overflow-wrap: anywhere }), 24 (44px min tap
targets for .cite, .chip, .source > a, .linklike, .quote-details summary on coarse
pointers — padding or ::after hit area, layout must not visibly bloat on desktop),
31 (.answer.refusal .answer-text b/strong { color: var(--ink) } — accent stays on
white cards only), 32 (busy/disabled ask button: bg #8a877c + aria acceptable), 33
(summary::-webkit-details-marker { display:none }), header ≤640px compression to
~≤130px total (smaller brand, tighter toggles), new classes: .cancel-btn (quiet,
hairline, sits beside .thinking), .retry-btn (accent-bordered, white bg), .badge.incomplete
(amber tone, AA on its surface), .notice-warn (amber bar under header).

## Verification (every agent)
`npm run typecheck` clean. No edits outside your territory. Report per finding:
fixed/deferred+why.
