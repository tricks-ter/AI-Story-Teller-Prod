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

export async function fetchMe() {
  const t = getToken();
  if (!t) return null;
  try {
    const r = await fetch(`${BASE_URL}/auth/me`, { headers: authHeaders() });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}
