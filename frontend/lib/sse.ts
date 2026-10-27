import { API_BASE } from "./config";
import type { Answer } from "./types";

/** If response headers haven't arrived by then, the transport is broken (e.g. a
 * proxy buffering the SSE response) — abort so the caller can fall back. The
 * backend sends headers immediately, before retrieval even starts. */
const HEADER_TIMEOUT_MS = 8000;

/** Max quiet time between SSE events once headers have arrived. A healthy
 * stream emits deltas continuously; a stalled one would otherwise lock the UI
 * forever (readOnly input + disabled button). */
const DEFAULT_IDLE_TIMEOUT_MS = 90_000;

export type StreamHandlers = {
  /** Called once per parsed SSE event (any type), before it is handled. */
  onEvent?: () => void;
  /** Called for each `delta` event with the raw text fragment. */
  onDelta: (text: string) => void;
};

export type StreamOptions = {
  /** Caller-owned abort (Cancel button). Aborting rejects streamChat with the
   * signal's reason — a DOMException named "AbortError" for a plain
   * `controller.abort()` — during both the header phase and the body read. */
  signal?: AbortSignal;
  /** Max ms between SSE events before rejecting with Error("stream_idle"). */
  idleTimeoutMs?: number;
};

type Frame = { event: string; data: string };

function parseFrame(frame: string): Frame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of frame.split("\n")) {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

/**
 * POST /api/chat/stream and parse the SSE response from a fetch
 * ReadableStream. Frames are split on blank lines (`\n\n`); events per the
 * API contract: `delta` {text}, `final` {Answer}, `error` {code}.
 *
 * Resolves with the final Answer. Rejects with:
 * - the caller signal's AbortError when `opts.signal` aborts (header phase or
 *   body read — callers can distinguish a user cancel by `err.name`);
 * - Error("stream_idle") when no SSE event arrives for `idleTimeoutMs`
 *   (default 90s);
 * - Error("stream_header_timeout") when headers don't arrive within 8s;
 * - an Error carrying the backend's error `code` on an `error` event;
 * - a plain Error on network failure, a malformed `final` frame, or a stream
 *   that ends without a `final` event.
 *
 * A malformed `delta` frame is skipped with a console.warn — it must not
 * discard an already-streamed answer. The body stream is always cancelled on
 * the way out (early final, error, abort) so the connection is released.
 *
 * Callers can use `onEvent` to know whether any event arrived before a
 * failure (the contract fallback to POST /api/chat applies only when none
 * did).
 */
export async function streamChat(
  body: unknown,
  handlers: StreamHandlers,
  opts: StreamOptions = {}
): Promise<Answer> {
  const { signal } = opts;
  const idleTimeoutMs = opts.idleTimeoutMs ?? DEFAULT_IDLE_TIMEOUT_MS;
  if (signal?.aborted) {
    throw signal.reason ?? new DOMException("The operation was aborted.", "AbortError");
  }

  // One internal controller drives the fetch. The caller's signal is chained
  // into it (works everywhere; AbortSignal.any is not yet universal), and
  // internal timeouts abort it with a distinguishable reason. Older runtimes
  // ignore the abort(reason) argument, so `internalReason` is also tracked
  // locally and re-thrown in place of a bare AbortError.
  const ctrl = new AbortController();
  let internalReason: Error | null = null;
  const abortInternal = (reason: Error) => {
    internalReason = reason;
    ctrl.abort(reason);
  };
  const onCallerAbort = () => ctrl.abort(signal?.reason);
  signal?.addEventListener("abort", onCallerAbort, { once: true });

  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  const resetIdle = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => abortInternal(new Error("stream_idle")), idleTimeoutMs);
  };

  const handle = (raw: string): Answer | null => {
    const frame = parseFrame(raw);
    if (!frame) return null;
    resetIdle();
    handlers.onEvent?.();
    if (frame.event === "delta") {
      // Finding 28: one malformed delta must not discard the streamed answer.
      try {
        const parsed = JSON.parse(frame.data) as { text?: unknown };
        if (typeof parsed.text === "string") handlers.onDelta(parsed.text);
      } catch {
        console.warn("skipping malformed SSE delta frame");
      }
      return null;
    }
    if (frame.event === "final") {
      // A malformed final is fatal: there is no answer to salvage.
      return JSON.parse(frame.data) as Answer;
    }
    if (frame.event === "error") {
      let code = "stream_error";
      try {
        const parsed = JSON.parse(frame.data) as { code?: unknown };
        if (typeof parsed.code === "string" && parsed.code) code = parsed.code;
      } catch {
        /* fall through with the generic code */
      }
      throw new Error(code);
    }
    return null;
  };

  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    const headerTimer = setTimeout(
      () => abortInternal(new Error("stream_header_timeout")),
      HEADER_TIMEOUT_MS
    );
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
    } finally {
      clearTimeout(headerTimer);
    }
    if (!res.ok || !res.body) {
      throw new Error(`stream unavailable (${res.status})`);
    }

    reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    resetIdle();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buf.indexOf("\n\n")) !== -1) {
        const raw = buf.slice(0, sep);
        buf = buf.slice(sep + 2);
        if (raw.trim()) {
          const final = handle(raw);
          if (final) return final;
        }
      }
    }
    // Flush a trailing frame not terminated by a blank line.
    if (buf.trim()) {
      const final = handle(buf);
      if (final) return final;
    }
    throw new Error("stream ended without a final answer");
  } catch (err) {
    // Map an internal-timeout abort back to its cause; runtimes that support
    // abort reasons already throw `internalReason` itself. A caller abort
    // (internalReason null) and real errors pass through untouched.
    if (internalReason && (err === internalReason || isAbortError(err))) {
      throw internalReason;
    }
    throw err;
  } finally {
    clearTimeout(idleTimer);
    signal?.removeEventListener("abort", onCallerAbort);
    if (reader) {
      // Finding 27: release the connection on every exit path (early final,
      // error event, abort). Best-effort — an errored stream rejects here.
      try {
        await reader.cancel();
      } catch {
        /* already errored/aborted — nothing to release */
      }
    }
  }
}
