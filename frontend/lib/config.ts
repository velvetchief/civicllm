/** Tenant served by this deployment. All tenant-specific copy comes from the API.
 * Override per-deployment with NEXT_PUBLIC_TENANT (baked in at build time). */
export const TENANT = process.env.NEXT_PUBLIC_TENANT ?? "brownsville";

/** Base URL for the backend API. Empty string = same origin (production, behind a
 * reverse proxy that handles SSE). In dev, set NEXT_PUBLIC_API_BASE to the FastAPI
 * origin — the Next dev proxy buffers/hangs SSE POST responses. */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export const LANG_STORAGE_KEY = "civicllm.lang";
export const SCOPE_STORAGE_KEY = "civicllm.scopeDismissed";

/** Show internal dev controls (provider switch). Off for real deployments;
 * enable locally with NEXT_PUBLIC_DEV_CONTROLS=1. */
export const SHOW_DEV_CONTROLS = process.env.NEXT_PUBLIC_DEV_CONTROLS === "1";

/** Guarded localStorage helpers — storage can throw in sandboxed iframes. */
export function storageGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
export function storageSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable — feature degrades to per-session */
  }
}
