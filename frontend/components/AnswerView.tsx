"use client";

import { useId, useState } from "react";
import { STRINGS } from "@/lib/i18n";
import { renderAnswerText, safeHref, stripMarkdown } from "@/lib/markdownLite";
import type { Answer, Lang, NextStep, RelatedRule, Source } from "@/lib/types";

// The answer anatomy, top to bottom (PRODUCT-UX doctrine #1):
// answer text (markdown-lite + citation chips) → source cards with the quoted
// code text expandable inline → related-rules strip → next-steps handoff card.
// A refusal renders as a calm, distinct card with the handoff prominent — a
// refusal that routes correctly is a successful outcome, not an error.
//
// Sources are renumbered client-side: retrieval numbers (which can be sparse,
// e.g. a lone "[4]") are remapped to display numbers 1..k. The numberMap keeps
// inline [n] markers, chips, cards and the clipboard export consistent.

export function AnswerView({
  a,
  lang,
  staffTools,
}: {
  a: Answer;
  lang: Lang;
  staffTools: boolean;
}) {
  const t = STRINGS[lang];
  const reactId = useId();
  const prefix = `ans-${a.answer_id ?? reactId}`;
  const related = a.related ?? [];
  const nextSteps = a.next_steps ?? [];

  // Renumber: order by retrieval number, assign display numbers 1..k.
  const retrieved = (a.sources ?? [])
    .slice()
    .sort((x, y) => x.number - y.number);
  const numberMap = new Map<number, number>();
  const displaySources: Source[] = retrieved.map((s, i) => {
    numberMap.set(s.number, i + 1);
    return { ...s, number: i + 1 };
  });

  function jumpToSource(n: number) {
    const el = document.getElementById(`${prefix}-src-${n}`);
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.focus({ preventScroll: true });
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
    // One flash timer per element: rapid clicks reset the timer instead of an
    // older timeout stripping the class out from under the newest flash.
    const pending = el.dataset.flashTimer;
    if (pending) window.clearTimeout(Number(pending));
    el.classList.remove("flash");
    void el.offsetWidth; // reflow so re-adding restarts the animation
    el.classList.add("flash");
    el.dataset.flashTimer = String(
      window.setTimeout(() => {
        el.classList.remove("flash");
        delete el.dataset.flashTimer;
      }, 1600)
    );
  }

  return (
    <div className="answer-block">
      <div className={a.refused ? "answer refusal" : "answer"}>
        <div className="answer-text">
          {renderAnswerText(a.text, retrieved, {
            anchorPrefix: prefix,
            lang,
            onCite: jumpToSource,
            numberMap,
          })}
        </div>
      </div>

      <div className="meta">
        {a.grounded && !a.refused && (
          <span className="badge grounded">✓ {t.groundedBadge}</span>
        )}
        {a.refused && <span className="badge routed">→ {t.refusalBadge}</span>}
        <span className="badge provider">{t.providerName(a.provider)}</span>
      </div>

      {displaySources.length > 0 && (
        <section className="sources" aria-label={t.sourcesHeading}>
          <h3>{t.sourcesHeading}</h3>
          <ol>
            {displaySources.map((s) => (
              <SourceCard key={s.number} s={s} prefix={prefix} lang={lang} />
            ))}
          </ol>
        </section>
      )}

      {related.length > 0 && (
        <section className="related" aria-label={t.relatedHeading}>
          <h3>{t.relatedHeading}</h3>
          <ul className="chips">
            {related.map((r, i) => (
              <li key={i}>
                <RelatedChip r={r} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {nextSteps.length > 0 && (
        <section
          className={a.refused ? "steps prominent" : "steps"}
          aria-label={t.nextStepsHeading}
        >
          <h3>{t.nextStepsHeading}</h3>
          <ul>
            {nextSteps.map((step, i) => (
              <NextStepItem key={i} step={step} />
            ))}
          </ul>
        </section>
      )}

      {a.disclaimer && <p className="disclaimer">{a.disclaimer}</p>}

      {staffTools && a.answer_id && (
        <div className="tools">
          <CopyButton
            label={t.copyCitations}
            doneLabel={t.copied}
            getText={() => citationText(a.text, displaySources, numberMap)}
          />
          <CopyButton
            label={t.copyLink}
            doneLabel={t.copied}
            getText={() => `${window.location.origin}/a/${a.answer_id}`}
          />
        </div>
      )}
    </div>
  );
}

function SourceCard({
  s,
  prefix,
  lang,
}: {
  s: Source;
  prefix: string;
  lang: Lang;
}) {
  const t = STRINGS[lang];
  const href = safeHref(s.source_url);
  return (
    <li className="source" id={`${prefix}-src-${s.number}`} tabIndex={-1}>
      {/* Section refs, titles and hierarchy come from the English corpus and
          are never translated, so they carry lang="en" (like the quote). */}
      <p className="source-head">
        <span className="num" aria-hidden="true">
          [{s.number}]
        </span>
        <b lang="en">{s.section_ref ?? s.title}</b>
      </p>
      {s.section_ref && (
        <p className="source-title" lang="en">
          {s.title}
        </p>
      )}
      {s.hierarchy.length > 0 && (
        <p className="crumb" lang="en">
          {s.hierarchy.join(" › ")}
        </p>
      )}
      {s.quote && (
        <details className="quote-details">
          <summary>{t.readCode}</summary>
          {/* The legal text is English and is never translated. */}
          <blockquote className="quote" lang="en">
            {s.quote}
          </blockquote>
        </details>
      )}
      {href && (
        <a href={href} target="_blank" rel="noreferrer">
          {t.viewSource}
        </a>
      )}
    </li>
  );
}

function RelatedChip({ r }: { r: RelatedRule }) {
  // Related rules are English corpus citations, never translated.
  const label = r.section_ref ?? r.title;
  const href = safeHref(r.source_url);
  if (href) {
    return (
      <a
        className="chip"
        href={href}
        target="_blank"
        rel="noreferrer"
        title={r.title}
        lang="en"
      >
        {label}
      </a>
    );
  }
  return (
    <span className="chip" title={r.title} lang="en">
      {label}
    </span>
  );
}

function NextStepItem({ step }: { step: NextStep }) {
  const href = safeHref(step.url);
  return (
    <li>
      {href ? (
        <a href={href} target="_blank" rel="noreferrer">
          <b>{step.label}</b>
        </a>
      ) : (
        <b>{step.label}</b>
      )}
      {step.detail && <span className="step-detail">{step.detail}</span>}
    </li>
  );
}

function CopyButton({
  label,
  doneLabel,
  getText,
}: {
  label: string;
  doneLabel: string;
  getText: () => string;
}) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="tool"
      onClick={async () => {
        const text = getText();
        let ok = false;
        try {
          await navigator.clipboard.writeText(text);
          ok = true;
        } catch {
          ok = legacyCopy(text);
        }
        if (ok) {
          setDone(true);
          window.setTimeout(() => setDone(false), 1800);
        }
      }}
    >
      {done ? doneLabel : label}
    </button>
  );
}

/** Fallback for contexts where the async Clipboard API is unavailable. */
function legacyCopy(text: string): boolean {
  const previouslyFocused = document.activeElement;
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  // Selecting the textarea moved focus; hand it back to the trigger button.
  if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
  return ok;
}

/**
 * Plain-text export: stripped answer with its inline [n] markers kept — but
 * remapped to DISPLAY numbers, matching the on-screen chips — plus a
 * "Sources:" list with one `[display] ` line per source, so the markers in
 * the pasted text map onto the list. Unmapped [n] stays as-is (matches the
 * literal rendering on screen).
 */
function citationText(
  text: string,
  displaySources: Source[],
  numberMap: Map<number, number>
): string {
  const body = stripMarkdown(text)
    .replace(/\[(\d{1,3})\]/g, (whole, d: string) => {
      const display = numberMap.get(Number(d));
      return display === undefined ? whole : `[${display}]`;
    })
    .trim();
  if (displaySources.length === 0) return body;
  const lines = displaySources.map(
    (s) =>
      `[${s.number}] ` +
      [s.section_ref, s.title, s.source_url].filter(Boolean).join(" — ")
  );
  return `${body}\n\nSources:\n${lines.join("\n")}`;
}
