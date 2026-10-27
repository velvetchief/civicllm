"use client";

import { useEffect, useRef, useState } from "react";
import { AnswerView } from "@/components/AnswerView";
import { ChannelList } from "@/components/ChannelList";
import {
  API_BASE,
  LANG_STORAGE_KEY,
  SCOPE_STORAGE_KEY,
  SHOW_DEV_CONTROLS,
  storageGet,
  storageSet,
  TENANT,
} from "@/lib/config";
import { STRINGS } from "@/lib/i18n";
import { renderAnswerText } from "@/lib/markdownLite";
import { streamChat } from "@/lib/sse";
import type { Answer, Lang, Mode, Provider, TenantInfo } from "@/lib/types";

type Turn = {
  question: string;
  /** Language snapshotted at ask time — turn chrome never re-renders in a
   * different language when the live toggle changes. */
  lang: Lang;
  /** Mode snapshotted at ask time — staff tools never appear on answers that
   * were asked as a resident (and vice versa). */
  mode: Mode;
  /** Accumulated streamed text before the final Answer arrives. */
  stream?: string;
  answer?: Answer;
  /** Friendly error state. Raw error detail goes to console.error only. */
  error?: boolean;
  canceled?: boolean;
};

const STAGE_DELAYS_MS = [3000, 12000, 30000];

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

export default function Home() {
  const [tenant, setTenant] = useState<TenantInfo | null>(null);
  const [tenantFailed, setTenantFailed] = useState(false);
  const [mode, setMode] = useState<Mode>("public");
  // Web default is Claude Sonnet; the private/Ollama model is opt-in via the
  // dev-controls switcher (local deployments only).
  const [provider, setProvider] = useState<Provider>("anthropic");
  const [langPref, setLangPref] = useState<Lang>("en");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [live, setLive] = useState("");
  const [scopeOpen, setScopeOpen] = useState(false);
  const [scopeFocusPending, setScopeFocusPending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const scopeRef = useRef<HTMLDivElement>(null);
  const turnCount = useRef(0);
  /** In-flight guard — a ref, not state, so a double submit racing React's
   * flush cannot start two requests. */
  const inFlight = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  // The Spanish toggle exists in Resident (public) mode only; staff mode is en.
  const lang: Lang = mode === "public" ? langPref : "en";
  const t = STRINGS[lang];

  // Tenant info, with one retry after 2s before declaring failure.
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetch(`${API_BASE}/api/tenants/${TENANT}`).then((r) => {
        if (!r.ok) throw new Error(`tenant fetch failed (${r.status})`);
        return r.json() as Promise<TenantInfo>;
      });
    load()
      .catch(
        () =>
          new Promise((resolve) => setTimeout(resolve, 2000)).then(load)
      )
      .then((info) => {
        if (!cancelled) setTenant(info);
      })
      .catch((err) => {
        console.error("tenant load failed:", err);
        if (!cancelled) setTenantFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Restore persisted language + scope-notice dismissal (client-only state).
  useEffect(() => {
    const saved = storageGet(LANG_STORAGE_KEY);
    if (saved === "en" || saved === "es") setLangPref(saved);
    if (!storageGet(SCOPE_STORAGE_KEY)) setScopeOpen(true);
  }, []);

  // Keep the document language (and title) in sync with the live UI language.
  useEffect(() => {
    document.documentElement.lang = lang;
    const brand = tenant?.display_name ?? t.fallbackBrand;
    document.title = `${brand} — ${t.tagline(tenant?.corpus_name ?? t.fallbackCorpus)}`;
  }, [lang, tenant, t]);

  // Scroll only when a new turn is added — never on streaming deltas.
  useEffect(() => {
    if (turns.length > turnCount.current) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      bottomRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
    }
    turnCount.current = turns.length;
  }, [turns]);

  // Staged progress copy: 0s searching / 3s reading / 12s stillWorking / 30s almostThere.
  useEffect(() => {
    if (!busy) return;
    setStage(0);
    const ids = STAGE_DELAYS_MS.map((ms, i) =>
      window.setTimeout(() => setStage(i + 1), ms)
    );
    return () => ids.forEach((id) => window.clearTimeout(id));
  }, [busy]);

  // "About this tool" → open the scope notice, then scroll to + focus it once
  // it has committed to the DOM.
  useEffect(() => {
    if (!scopeFocusPending || !scopeOpen) return;
    const el = scopeRef.current;
    if (el) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
      el.focus({ preventScroll: true });
    }
    setScopeFocusPending(false);
  }, [scopeFocusPending, scopeOpen]);

  function chooseLang(l: Lang) {
    setLangPref(l);
    storageSet(LANG_STORAGE_KEY, l);
  }

  function dismissScope() {
    setScopeOpen(false);
    storageSet(SCOPE_STORAGE_KEY, "1");
  }

  function openScope() {
    setScopeOpen(true);
    setScopeFocusPending(true);
  }

  function cancelAsk() {
    abortRef.current?.abort();
  }

  async function ask(question: string, snapshot?: { lang: Lang; mode: Mode }) {
    const q = question.trim();
    if (!q || inFlight.current) return;
    inFlight.current = true;

    // Snapshot { lang, mode } at ask time; the turn renders from this snapshot
    // forever, regardless of later toggle flips.
    const turnLang = snapshot?.lang ?? lang;
    const turnMode = snapshot?.mode ?? mode;
    const tt = STRINGS[turnLang];

    setBusy(true);
    setStage(0);
    setInput("");
    setLive(tt.announceSubmitted);
    setTurns((prev) => [...prev, { question: q, lang: turnLang, mode: turnMode }]);
    // Keep keyboard users anchored: focus returns to the (readOnly) input even
    // when the ask came from an example button that is about to unmount.
    inputRef.current?.focus();

    const controller = new AbortController();
    abortRef.current = controller;

    const body = {
      tenant: TENANT,
      mode: turnMode,
      message: q,
      provider,
      language: turnLang,
    };
    const updateLast = (patch: Partial<Turn>) =>
      setTurns((prev) =>
        prev.map((turn, i) => (i === prev.length - 1 ? { ...turn, ...patch } : turn))
      );

    let gotEvent = false;
    let announced = false;
    try {
      const answer = await streamChat(
        body,
        {
          onEvent: () => {
            gotEvent = true;
          },
          onDelta: (chunk) => {
            if (!announced) {
              announced = true;
              setLive(tt.announceArriving);
            }
            setTurns((prev) =>
              prev.map((turn, i) =>
                i === prev.length - 1
                  ? { ...turn, stream: (turn.stream ?? "") + chunk }
                  : turn
              )
            );
          },
        },
        { signal: controller.signal }
      );
      // `final` replaces the streamed text entirely (it may be a refusal).
      updateLast({ answer, stream: undefined });
      setLive(tt.announceComplete);
    } catch (err) {
      if (isAbortError(err)) {
        // User-initiated cancel: calm state, keep any partial text.
        updateLast({ canceled: true });
        setLive(tt.announceCanceled);
      } else if (!gotEvent) {
        // Stream failed before any event — fall back to the non-streaming API.
        console.error("stream failed before first event:", err);
        try {
          const res = await fetch(`${API_BASE}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
            signal: controller.signal,
          });
          if (!res.ok) throw new Error(`API error ${res.status}`);
          const answer = (await res.json()) as Answer;
          updateLast({ answer });
          setLive(tt.announceComplete);
        } catch (err2) {
          if (isAbortError(err2)) {
            updateLast({ canceled: true });
            setLive(tt.announceCanceled);
          } else {
            console.error("chat fallback failed:", err2);
            updateLast({ error: true });
            setLive(tt.announceError);
          }
        }
      } else {
        // Error mid-stream: keep the partial text; the turn renders it with an
        // "incomplete" badge above the friendly error block.
        console.error("stream failed mid-answer:", err);
        updateLast({ error: true });
        setLive(tt.announceError);
      }
    } finally {
      abortRef.current = null;
      inFlight.current = false;
      setBusy(false);
    }
  }

  const corpus = tenant?.corpus_name ?? t.fallbackCorpus;
  const examples =
    lang === "es" && tenant?.example_questions_es?.length
      ? tenant.example_questions_es
      : tenant?.example_questions ?? [];
  const scopeText =
    (lang === "es"
      ? tenant?.scope_statement_es || tenant?.scope_statement
      : tenant?.scope_statement) || t.scopeFallback;

  return (
    <div lang={lang}>
      <header className="top">
        <div className="shell">
          <div className="brand">
            <h1>{tenant?.display_name ?? t.fallbackBrand}</h1>
            <span>{t.tagline(corpus)}</span>
          </div>
          <div className="toggles">
            <div className="seg" role="group" aria-label={t.modeAria}>
              {(["public", "staff"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  className={mode === m ? "on" : ""}
                  aria-pressed={mode === m}
                  disabled={busy}
                  onClick={() => setMode(m)}
                >
                  {m === "public" ? t.modePublic : t.modeStaff}
                </button>
              ))}
            </div>
            {SHOW_DEV_CONTROLS && mode === "staff" && (
              <div className="seg" role="group" aria-label={t.providerAria}>
                {(["anthropic", "ollama"] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    className={provider === p ? "on" : ""}
                    aria-pressed={provider === p}
                    disabled={busy}
                    onClick={() => setProvider(p)}
                  >
                    {p === "ollama" ? t.providerPrivate : t.providerClaude}
                  </button>
                ))}
              </div>
            )}
            {mode === "public" && (
              <div className="seg" role="group" aria-label={t.langAria}>
                {(["en", "es"] as const).map((l) => (
                  <button
                    key={l}
                    type="button"
                    className={langPref === l ? "on" : ""}
                    aria-pressed={langPref === l}
                    lang={l}
                    disabled={busy}
                    onClick={() => chooseLang(l)}
                  >
                    {l === "en" ? "English" : "Español"}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="shell">
        {tenantFailed && (
          <div className="notice-warn" role="status">
            {t.tenantLoadFailed}
          </div>
        )}

        {scopeOpen && (
          <div className="scope" role="note" ref={scopeRef} tabIndex={-1}>
            <p>
              <b>{t.scopeTitle}.</b> {scopeText} {t.scopeStateless}
            </p>
            <button type="button" onClick={dismissScope}>
              {t.dismiss}
            </button>
          </div>
        )}

        {turns.length === 0 && (
          <div className="hero">
            <h2>{t.heroTitle}</h2>
            <p>{t.heroSub(corpus)}</p>
          </div>
        )}

        {turns.length === 0 && examples.length > 0 && (
          <>
            <p className="examples-label">{t.tryAsking}</p>
            <div className="examples">
              {examples.map((q) => (
                <button key={q} type="button" disabled={busy} onClick={() => ask(q)}>
                  {q}
                </button>
              ))}
            </div>
          </>
        )}

        {turns.map((turn, i) => {
          const isLast = i === turns.length - 1;
          // All turn chrome renders from the snapshot, never live state.
          const tt = STRINGS[turn.lang];
          const settled = Boolean(turn.answer || turn.error || turn.canceled);
          const stageText = [tt.searching, tt.reading, tt.stillWorking, tt.almostThere];
          // Once deltas arrive the timers' guesswork is moot — we are writing.
          const waitText = turn.stream ? tt.almostThere : stageText[stage];
          return (
            <section className="turn" key={i} lang={turn.lang}>
              <h2 className="q">
                <span className="q-label">{tt.youAsked}</span> {turn.question}
              </h2>

              {/* Partial streamed text stays visible; on error/cancel it gets
                  an "incomplete" badge instead of being discarded. */}
              {!turn.answer && turn.stream && (
                <div className="answer">
                  {(turn.error || turn.canceled) && (
                    <span className="badge incomplete">{tt.incompleteBadge}</span>
                  )}
                  <div className="answer-text">
                    {renderAnswerText(turn.stream, [], {
                      anchorPrefix: `turn-${i}`,
                      lang: turn.lang,
                    })}
                  </div>
                </div>
              )}

              {turn.canceled && <p className="thinking">{tt.canceled}</p>}

              {turn.error && (
                <div className="answer error" role="alert">
                  <p>
                    {tt.errorFriendly} {tt.errorRetryHint}
                  </p>
                  {tenant?.channels?.length ? (
                    <ChannelList
                      channels={tenant.channels}
                      lang={turn.lang}
                      heading={tt.nextStepsHeading}
                      prominent
                    />
                  ) : null}
                  <button
                    type="button"
                    className="retry-btn"
                    disabled={busy}
                    onClick={() =>
                      ask(turn.question, { lang: turn.lang, mode: turn.mode })
                    }
                  >
                    {tt.retry}
                  </button>
                </div>
              )}

              {/* Wait indicator + always-available cancel, from the first stage
                  and throughout streaming. */}
              {!settled && isLast && busy && (
                <p className="thinking">
                  {waitText}{" "}
                  <button type="button" className="cancel-btn" onClick={cancelAsk}>
                    {tt.cancel}
                  </button>
                </p>
              )}

              {turn.answer && (
                <AnswerView
                  a={turn.answer}
                  lang={turn.lang}
                  staffTools={turn.mode === "staff"}
                />
              )}
            </section>
          );
        })}
        <div ref={bottomRef} />

        <footer className="site">
          {tenant?.freshness && (
            // Always English — verbatim from the Municode supplement banner.
            <p className="fresh" lang="en">
              {tenant.freshness}
            </p>
          )}
          <p>
            {t.aiDisclosure}{" "}
            <button type="button" className="linklike" onClick={openScope}>
              {t.aboutLink}
            </button>
          </p>
        </footer>

        {/* Streaming status for screen readers; the token stream itself is
            intentionally NOT in the live region. */}
        <div aria-live="polite" role="status" className="visually-hidden">
          {live}
        </div>
      </main>

      <form
        className="ask"
        aria-label={t.askFormAria}
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <div className="inner">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t.askPlaceholder}
            aria-label={t.inputAria}
            // readOnly (not disabled) while busy so keyboard focus is not
            // dropped to <body> mid-request; ask() already guards re-entry.
            readOnly={busy}
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            aria-label={t.askButton}
          >
            {busy ? t.askBusy : t.askButton}
          </button>
        </div>
      </form>
    </div>
  );
}
