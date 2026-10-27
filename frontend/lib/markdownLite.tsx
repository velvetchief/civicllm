import type { ReactNode } from "react";
import { STRINGS } from "./i18n";
import type { Lang, Source } from "./types";

// Markdown-lite: per the API contract, ONLY `**bold**` and newlines are
// rendered; everything else is literal text. Output is built from React text
// nodes — no HTML injection path exists. Newlines are preserved by the
// `white-space: pre-wrap` on the answer container.
//
// Inline `[n]` markers that match a source number become superscript citation
// chips that jump to (and highlight) the matching source card. Unmatched
// `[n]` stays literal (e.g. while streaming, before sources arrive).
//
// Streaming niceties:
// - `[n]` markers are tokenized INSIDE `**bold**` spans too.
// - An unclosed `**` at the end of the text renders as bold-to-end, so no
//   literal asterisks flicker while a bolded figure is still streaming.

/** Closed `**bold**` span, or an unclosed `**…` running to end of text. */
const BOLD = /\*\*([^*]+)\*\*|\*\*([^*]*)$/g;
const CITE = /(\[\d{1,3}\])/g;
const CITE_EXACT = /^\[(\d{1,3})\]$/;

export type RenderOpts = {
  /** Unique per answer; source cards use ids `${anchorPrefix}-src-${n}`. */
  anchorPrefix: string;
  lang: Lang;
  onCite?: (n: number) => void;
  /**
   * Retrieval number → display number. When present, chips render (and are
   * announced and anchored by) the display number; a `[n]` with no mapping
   * stays literal. When absent, numbers pass through unchanged.
   */
  numberMap?: Map<number, number>;
};

export function renderAnswerText(
  text: string,
  sources: Source[],
  opts: RenderOpts
): ReactNode[] {
  const nodes: ReactNode[] = [];
  BOLD.lastIndex = 0;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = BOLD.exec(text)) !== null) {
    if (m.index > last) {
      nodes.push(...renderCitations(text.slice(last, m.index), sources, opts, `t${last}`));
    }
    // m[1]: closed bold; m[2]: unclosed bold-to-end (streaming).
    const inner = renderCitations(m[1] ?? m[2], sources, opts, `b${m.index}`);
    nodes.push(
      <strong key={`s${m.index}`}>
        {inner.length === 1 ? inner[0] : inner}
      </strong>
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    nodes.push(...renderCitations(text.slice(last), sources, opts, `t${last}`));
  }
  return nodes;
}

/** Tokenize `[n]` citation markers in a run of plain text. */
function renderCitations(
  text: string,
  sources: Source[],
  opts: RenderOpts,
  keyBase: string
): ReactNode[] {
  const t = STRINGS[opts.lang];
  return text.split(CITE).map((part, i) => {
    const m = CITE_EXACT.exec(part);
    if (!m) return part;
    const n = Number(m[1]);
    const src = sources.find((s) => s.number === n);
    const display = opts.numberMap ? opts.numberMap.get(n) : n;
    // No matching source, or no mapping for this retrieval number → literal.
    if (!src || display === undefined) return part;
    return (
      <sup key={`${keyBase}-${i}`} className="cite">
        <a
          href={`#${opts.anchorPrefix}-src-${display}`}
          aria-label={t.sourceAria(display, src.section_ref ?? src.title)}
          onClick={(e) => {
            if (opts.onCite) {
              e.preventDefault();
              opts.onCite(display);
            }
          }}
        >
          {display}
        </a>
      </sup>
    );
  });
}

/** Strip markdown-lite for plain-text export (clipboard). */
export function stripMarkdown(text: string): string {
  return text.replace(/\*\*/g, "");
}

/**
 * Only http/https URLs may be rendered as hrefs (API/tenant data is not
 * trusted to carry javascript:, data:, etc.). Returns the URL when safe,
 * otherwise null — callers render plain text instead of a link.
 */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const protocol = new URL(url).protocol;
    return protocol === "http:" || protocol === "https:" ? url : null;
  } catch {
    return null; // relative or unparseable — refuse rather than guess
  }
}
