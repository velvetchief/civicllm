// Shared types for the CivicLLM frontend, mirroring docs/API-CONTRACT.md.
// Fields added in contract v2 are typed optional where an older backend build
// might omit them, so the UI degrades gracefully instead of crashing.

export type Lang = "en" | "es";
export type Mode = "public" | "staff";
export type Provider = "ollama" | "anthropic";

export type Source = {
  number: number;
  title: string;
  hierarchy: string[];
  section_ref: string | null;
  source_url: string | null;
  excerpt: string;
  /** Full chunk text (capped at 2000 chars) for inline verification. */
  quote?: string;
};

export type RelatedRule = {
  title: string;
  section_ref: string | null;
  source_url: string | null;
};

export type NextStep = {
  label: string;
  detail?: string;
  url?: string | null;
};

/** Tenant handoff channel — carries both languages; pick at render time. */
export type Channel = NextStep & {
  label_es?: string;
  detail_es?: string;
};

export function channelToStep(c: Channel, lang: Lang): NextStep {
  if (lang === "es") {
    return { label: c.label_es || c.label, detail: c.detail_es || c.detail, url: c.url };
  }
  return { label: c.label, detail: c.detail, url: c.url };
}

export type Answer = {
  answer_id?: string;
  text: string;
  grounded: boolean;
  refused: boolean;
  provider: string;
  disclaimer: string;
  sources: Source[];
  related?: RelatedRule[];
  next_steps?: NextStep[];
};

export type TenantInfo = {
  id: string;
  display_name: string;
  corpus_name: string;
  modes: string[];
  languages?: string[];
  example_questions: string[];
  example_questions_es?: string[];
  scope_statement?: string;
  scope_statement_es?: string;
  freshness?: string | null;
  channels?: Channel[];
};

/** GET /api/answers/{id} response. */
export type AnswerRecord = {
  question: string;
  mode: Mode;
  language: string;
  created_at: string;
  answer: Answer;
};
