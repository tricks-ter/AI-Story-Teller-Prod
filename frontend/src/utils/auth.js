const TOKEN_KEY = "inkmind_token";
const USER_KEY = "inkmind_user";

export const BASE_URL = (() => {
  const env = import.meta.env.VITE_API_URL;
  if (env) return env.endsWith("/api") ? env : env + "/api";
  return "/api";
})();

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY); }
  catch { return null; }
}

export function getSavedUser() {
  try {
    const raw = localStorage.getItem(USER_KEY) || sessionStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function saveAuth(token, user, remember) {
  clearAuth();
  const store = remember ? localStorage : sessionStorage;
  store.setItem(TOKEN_KEY, token);
  store.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
  } catch {}
}

export function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

// ── Shared, always-visible error tooling (used by ALL future code) ──
export async function parseJsonSafe(res) {
  const text = await res.text();
  try { return JSON.parse(text); }
  catch { return { detail: `Server returned non-JSON: ${text.slice(0, 120)}` }; }
}

export function friendlyHttp(status, detail) {
  if (detail && typeof detail === "string" && detail.length < 140) return detail;
  if (status === 401) return "Invalid username or password.";
  if (status === 403) return "You don't have permission for that.";
  if (status === 404) return "Service not found (404) — backend may not be deployed yet.";
  if (status === 409) return "Already exists.";
  if (status >= 500) return `Server error (${status}). Please try again shortly.`;
  return `Something went wrong (HTTP ${status}).`;
}

export function describeNetworkError(err) {
  if (err?.name === "AbortError") return "Request timed out. Check your connection and try again.";
  if (err?.message === "Failed to fetch") return "Network error. Check your internet connection.";
  return err?.message || "Unexpected error.";
}

export async function fetchMe() {
  const t = getToken();
  if (!t) return null;
  try {
    const r = await fetch(`${BASE_URL}/auth/me`, { headers: authHeaders() });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}
