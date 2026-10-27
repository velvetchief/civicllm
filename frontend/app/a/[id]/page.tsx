"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { AnswerView } from "@/components/AnswerView";
import { API_BASE, TENANT } from "@/lib/config";
import { STRINGS } from "@/lib/i18n";
import type { AnswerRecord, Lang, TenantInfo } from "@/lib/types";

type State =
  | { status: "loading" }
  | { status: "notfound" }
  | { status: "error" }
  | { status: "ok"; record: AnswerRecord };

export default function PermalinkPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [state, setState] = useState<State>({ status: "loading" });
  const [tenant, setTenant] = useState<TenantInfo | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/tenants/${TENANT}`)
      .then((r) => (r.ok ? (r.json() as Promise<TenantInfo>) : null))
      .then(setTenant)
      .catch(() => setTenant(null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/answers/${encodeURIComponent(id)}`)
      .then(async (r) => {
        if (cancelled) return;
        if (r.status === 404) {
          setState({ status: "notfound" });
          return;
        }
        if (!r.ok) {
          console.error(`Permalink fetch failed: API ${r.status}`);
          setState({ status: "error" });
          return;
        }
        const record = (await r.json()) as AnswerRecord;
        if (!cancelled) setState({ status: "ok", record });
      })
      .catch((e) => {
        if (!cancelled) {
          console.error("Permalink fetch failed:", e);
          setState({ status: "error" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const lang: Lang =
    state.status === "ok" && state.record.language === "es" ? "es" : "en";
  const t = STRINGS[lang];

  // Screen-reader announcement for the loading → resolved transition; the
  // visual states below are not inside a live region of their own.
  const liveStatus =
    state.status === "loading"
      ? t.loading
      : state.status === "notfound"
        ? t.permalinkNotFound
        : state.status === "error"
          ? t.announceError
          : t.announceComplete;

  return (
    <div lang={lang}>
      <header className="top">
        <div className="shell">
          <div className="brand">
            <h1>
              <Link href="/" className="brand-link">
                {tenant?.display_name ?? t.fallbackBrand}
              </Link>
            </h1>
            <span>{t.tagline(tenant?.corpus_name ?? t.fallbackCorpus)}</span>
          </div>
        </div>
      </header>

      <main className="shell">
        <div aria-live="polite" role="status" className="visually-hidden">
          {liveStatus}
        </div>

        {state.status === "loading" && <p className="thinking">{t.loading}</p>}

        {state.status === "notfound" && (
          <div className="answer refusal">
            <p>{t.permalinkNotFound}</p>
            <p>
              <Link href="/">{t.backHome} →</Link>
            </p>
          </div>
        )}

        {state.status === "error" && (
          <div className="answer error" role="alert">
            <p>{t.errorFriendly}</p>
            <p>
              <Link href="/">{t.backHome} →</Link>
            </p>
          </div>
        )}

        {state.status === "ok" && (
          <>
            <section className="turn">
              <h2 className="q">
                <span className="q-label">{t.youAsked}</span>{" "}
                {state.record.question}
              </h2>
              <p className="answered-on">
                {t.answeredOn(formatAnsweredDate(state.record.created_at, lang))}
              </p>
              {/* Staff tools never render here: a permalink viewer's identity
                  is unknown, regardless of the mode the answer was asked in. */}
              <AnswerView
                a={state.record.answer}
                lang={lang}
                staffTools={false}
              />
            </section>
            <p className="follow-up-row">
              <Link className="follow-up" href="/">
                {t.followUp} →
              </Link>
            </p>
          </>
        )}
      </main>
    </div>
  );
}

/** "July 4, 2026" / "4 de julio de 2026"; raw string if the date is bad. */
function formatAnsweredDate(createdAt: string, lang: Lang): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return createdAt;
  return new Intl.DateTimeFormat(lang === "es" ? "es-MX" : "en-US", {
    dateStyle: "long",
  }).format(date);
}
