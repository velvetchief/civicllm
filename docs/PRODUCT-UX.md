# Who this is for, and how it should feel

Research-grounded personas and UX doctrine for CivicLLM. Sources: Austin DSD field
research + civic-AI evidence briefs (2026-07-04, agent research with citations; key
URLs inline). This document drives UI/UX decisions; PLAN.md drives engineering.

## The situation we're designing into (Austin facts)

- Getting a zoning answer today: call 311 → DSD line (7:45–4:45 M–F) → book a
  **20-minute PDC appointment** (Teams/in-person) → or email LUAssist (**2-business-day
  SLA**) → or pay for a **zoning verification letter (7–10 business days)**.
- Customer satisfaction with permitting measured at **3/10** (McKinsey 2023); the LDC
  has **~1,800 regulations**; the city's own 2014 diagnosis called the code
  "virtually unusable"; the CodeNEXT rewrite failed after ~$8M.
- An entire **permit-expediter industry ($75–300/hr)** exists largely to answer
  "what does the code allow on this property."
- Practitioners cope with homemade decoders (AIA Austin "Code Cards").
- Language/access: ~10% of residents speak English "less than very well" (45+
  languages); 28% of Hispanic adults are smartphone-only (Pew 2026); a city audit
  found 311's Spanish service "often unsuccessful."
- DSD staff reality: reviewer inconsistency is a documented builder complaint; new
  reviewers take 6–12 months to ramp; turnover is high; a **Code Interpretation
  Library** (~40 memos) holds official interpretations; the Development Officer must
  answer formal interpretation requests within 60 days.

## Personas

### Staff (behind Entra ID SSO — the Phase 1 pilot users)

| # | Persona | Reality | What they need from us | Success metric |
|---|---|---|---|---|
| S1 | **Front-door triager** (311 agent, permit tech) | Not a code expert; six systems open; measured on handle time; fields the 20+ daily "can I…" calls | 30-second plain answer + confident routing ("that's a PDC zoning appointment") + send-to-caller link | Handle time ↓, transfers ↓ |
| S2 | **Zoning reviewer / LUAssist case manager** | Answers the same setback/ADU/HOME questions all day on a 2-day email SLA; personally blamed for inconsistency between colleagues | Draft-quality cited answer to verify & paste into email; identical answer to what their colleague would get | Email turnaround ↓, consistency complaints ↓ |
| S3 | **Plans examiner / new reviewer** | Licensed, scarce, 6–12 months to ramp; must chase base zone → overlays → Subchapter F → interpretation memos | Full reasoning chain across sections; interpretation memos surfaced beside code text; deep links | Ramp time ↓ (the PA-pilot effect: staff AI saved ~95 min/day) |
| S4 | **Development Officer / senior interpreter** | Owns formal interpretations (60-day clock); sees code ambiguity as legal risk | Tool that never invents interpretations and clearly separates code text from interpretation memos; query-log signal showing where the code confuses people | Interpretation backlog ↓; ambiguity hotspots visible |

### Public (Phase 2/3)

| # | Persona | Reality | What they need from us | Success metric |
|---|---|---|---|---|
| P1 | **Homeowner-dreamer** (ADU / garage conversion / HOME lot) | Phone, evenings; doesn't know "impervious cover"; possibly Spanish-first; today faces a 20-min appointment booking or an expediter | Plain answer + "what this means for you" + concrete next step | Self-serves the basics without an expediter |
| P2 | **Small builder / GC** | Phone, in a truck between sites; semi-fluent in code | The SF-3 numbers in 10 seconds; quotable text to settle disputes | Repeat daily use |
| P3 | **Architect / permit expediter** | Desktop power user; skeptical; will stress-test; today uses AIA Code Cards + memory | Section numbers, cross-references, permalinks to share with clients | Prefers us to their own notes |
| P4 | **Realtor** | Needs zoning facts during listing/due diligence; today waits 7–10 days for a verification letter | Instant informal answer + clear handoff to the formal letter when required | Letter requests become informed, not exploratory |
| P5 | **Concerned neighbor / renter / small business** | "Can my neighbor build that?" — emotionally loaded; or needs zoning confirmation for a license | Neutral plain answer + the right channel (311 complaint / DSDZoningSitePlan email) | Complaints routed right the first time |

Cross-cutting: limited-English (Spanish first), low-literacy (target ~6th-grade in
resident mode; 28% of US adults at/below PIAAC Level 1), smartphone-only, WCAG 2.1 AA.

## UX doctrine (each rule earned by evidence)

1. **The answer is the unit of design.** Anatomy, top to bottom: direct answer with
   the figure bolded → plain-language "what this means" (resident mode) → **the quoted
   code text inline, expandable** → citation chip linking to Municode → "related rules
   that often apply" (overlays: McMansion/Subchapter F, impervious cover, HOME) →
   next-step handoff. Rationale: users click AI citations ~1% of the time (Pew 2025),
   and citations inflate trust even when wrong (arXiv:2501.01303) — so the
   verification must be *in* the answer, not behind a link.
2. **Refusals hand off, never dead-end** (Google PAIR): every refusal offers the real
   channels — book the 20-min PDC zoning appointment, LUAssist email (2-day SLA),
   311, phone hours. A refusal that routes correctly is a *successful* outcome.
3. **Scope statement on first use** (Microsoft HAX G1/G2): "I answer questions about
   Austin's Land Development Code. I can't give legal advice, decide your case, or
   see your property's permit history." NYC's MyCity bot answered everything —
   including illegally; it also contradicted its own disclaimer. Disclaimers are not
   a safety layer (Air Canada was held liable despite one); grounding + refusal is.
4. **Consistency is a trust feature.** MyCity gave different users different answers
   to the same question. We: temperature ~0, canonical reviewed answers for top
   questions (fed by a staff answer-review workflow),
   published FAQ cards from query logs.
5. **Verbal, calibrated uncertainty — no confidence percentages.** First-person
   hedges measurably reduce overreliance (FAccT 2024); numeric scores aren't
   validated. "I'm not certain — this lot may be affected by the HOME amendments"
   beats "Confidence: 74%".
6. **Resident mode is mobile-first, 6th-grade, bilingual.** Thumb-reachable input,
   answer readable without scroll on a cheap Android, Spanish toggle from day one
   (the city publishes in 10 languages; its Spanish 311 service is documented as
   failing — being *good* at Spanish is a differentiator).
7. **Staff mode is a desktop workbench, not a chat toy.** Copy-with-citation (pastes
   answer + section refs into LUAssist emails), reasoning chain view, Code
   Interpretation Library results visually distinct from code text, flag-for-
   correction (6.4.1.2), permalinks so two reviewers share one answer.
8. **Freshness is a visible trust signal.** "Code current through Supp. 173 (Ord.
   20260122-059, eff. Feb 2, 2026)" in the footer — directly monetizes our 10-day
   refresh SLA as UX.
9. **Accessibility is a contractual floor, not polish**: WCAG 2.1 AA (ADA Title II
   deadline for Austin-size cities: April 26, 2027), full keyboard flow, live-region
   announcements while the answer streams, reflow at 400% zoom.
10. **The product is also a sensor.** Query logs (PIA-compliant) show DSD exactly
    where the code confuses the public — input for the Development Officer's
    interpretation priorities and the city's FAQ. This is the feature that makes the
    city renew.

## Platform decisions

- **Responsive web, no native app.** Nobody installs a city app to ask one question;
  smartphone-dependent users are the target and the browser is free. PWA-grade
  performance budget (works on mid-tier Android over cellular).
- **Embeddable widget** later: austintexas.gov relaunched March 2026 — position the
  resident mode as an embed there and inside the AB+C portal's existing live-chat slot.
- **Staff mode at a desk**: desktop-density UI behind Entra ID SSO; also the 311
  agent's screen. Same engine, different tenant-mode config.
- **Property-aware answers are the roadmap's killer feature**: the real question is
  never "what is SF-3" but "what can I build at *my address*." Phase: (1) user picks
  district manually (now), (2) address → district via the city's Property Profile
  GIS/open data (Phase 2), (3) parcel-aware overlays (Phase 3). Complements — does
  not compete with — the city's Archistar plan-review automation ($3.5M contract):
  they check drawings; we answer questions.

## Near-term UI backlog implied by all this — SHIPPED 2026-07-05

All items below were implemented (multi-agent build: backend + frontend workstreams
against docs/API-CONTRACT.md, then integration + a11y audit). Eval stayed 10/10.

- [x] Answer anatomy v2: bolded figure, inline expandable quoted code text
      ("Read the code text"), related-rules strip, next-step handoff card
- [x] Refusal card with real Austin channels (PDC 20-min appointment, LUAssist
      email w/ 2-day SLA, DSD phone + 311)
- [x] Scope statement on first load (dismissible, localStorage, reopenable from footer)
- [x] Spanish toggle (resident mode): UI chrome i18n + Spanish generation +
      cross-lingual retrieval (query translated to English for search only) +
      localized disclaimer/refusal/next-steps; English legal text marked lang="en"
- [x] Copy-with-citation button (staff mode); answer permalinks (`/a/{id}`, answers
      table — also the seed of the PIA log / answer-review store)
- [x] Corpus-freshness footer (Municode supplement banner captured at ingest)
- [x] Streaming (SSE) with sentinel holdback + aria-live status announcements
- [x] Mobile pass (360px clean, 44px+ touch targets, reduced-motion, 16px inputs)
- [x] Accessibility: axe-core 0 violations on both routes (desktop + mobile);
      contrast ratios computed and passing; keyboard focus preserved during requests

Still open (needs a real browser, not the embedded preview): confirm clipboard
buttons ("Copy with citations", "Copy link") work; execCommand fallback is in place.
