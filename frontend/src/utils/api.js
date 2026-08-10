import { BASE_URL, authHeaders, withTelemetry, parseJsonSafe } from "./auth";

export { BASE_URL };

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function clampRetryAfter(v) {
  const n = parseFloat(v);
  if (!isFinite(n) || n <= 0) return 3;
  return Math.min(10, Math.max(1, n));
}

async function runStream(url, body, controller, onEvent, onError) {
  const MAX_ATTEMPTS = 2;
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    let res;
    try {
      const enriched = await withTelemetry(body);
      res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(enriched),
        signal: controller.signal,
      });
    } catch (err) {
      if (err.name !== "AbortError") onError(err);
      return;
    }

    if (res.status === 429) {
      if (attempt < MAX_ATTEMPTS - 1) {
        const ra = clampRetryAfter(res.headers.get("Retry-After"));
        onEvent({ type: "status", message: `Rate limited (429) — retrying in ${Math.ceil(ra)}s…` });
        await sleep(ra * 1000);
        continue;
      }
      onError(new Error("The AI engine is rate-limited (429). Please wait a moment and try again."));
      return;
    }
    if (!res.ok || !res.body) { onError(new Error(`HTTP ${res.status}`)); return; }

    let streamed = false;
    let retryInfo = null;
    let sawTerminal = false;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    try {
      outer: while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const line = chunk.trim();
          if (!line.startsWith("data:")) continue;
          let ev;
          try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
          if (ev.type === "content") streamed = true;
          if (ev.type === "done" || ev.type === "error") sawTerminal = true;
          if (ev.type === "error" && ev.code === 429 && !streamed) { retryInfo = ev; break outer; }
          onEvent(ev);
          if (ev.type === "error" || ev.type === "done") return;
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") onError(err);
      return;
    }

    if (retryInfo && attempt < MAX_ATTEMPTS - 1) {
      const ra = clampRetryAfter(retryInfo.retry_after);
      onEvent({ type: "status", message: `Rate limited (429) — retrying in ${Math.ceil(ra)}s…` });
      await sleep(ra * 1000);
      continue;
    }
    if (retryInfo) {
      onEvent({ type: "error", message: retryInfo.message || "The AI engine is rate-limited (429). Please wait a moment and try again." });
      return;
    }
    if (!sawTerminal) onEvent({ type: "done" });
    return;
  }
}

export function streamChat(sessionId, messages, settings, onEvent, onError) {
  const controller = new AbortController();
  const body = {
    session_id: sessionId,
    messages,
    model: settings?.model ?? "glm-4.7-flash",
    max_tokens: settings?.maxTokens ?? 4096,
    temperature: settings?.temperature ?? 0.7,
    enable_thinking: settings?.enableThinking ?? true,
  };
  runStream(`${BASE_URL}/chat/stream`, body, controller, onEvent, onError);
  return () => controller.abort();
}

export function streamStory(storyId, userAction, settings, onEvent, onError) {
  const controller = new AbortController();
  const body = {
    user_action: userAction,
    model: settings?.model ?? "glm-4.7-flash",
    max_tokens: settings?.maxTokens ?? 4096,
    temperature: settings?.temperature ?? 0.7,
    enable_thinking: settings?.enableThinking ?? true,
  };
  runStream(`${BASE_URL}/stories/${storyId}/continue`, body, controller, onEvent, onError);
  return () => controller.abort();
}

async function postAction(path, payload) {
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    });
    const data = await parseJsonSafe(res);
    if (!res.ok) return { ok: false, detail: data?.detail || `HTTP ${res.status}` };
    return { ok: true, data };
  } catch {
    return { ok: false, detail: "Connection error" };
  }
}

export async function fetchInventory(playthroughId) {
  try {
    const res = await fetch(`${BASE_URL}/playthroughs/${playthroughId}/inventory`, { headers: authHeaders() });
    const data = await parseJsonSafe(res);
    if (!res.ok) return null;
    return data;
  } catch { return null; }
}

export async function fetchMap(playthroughId) {
  try {
    const res = await fetch(`${BASE_URL}/playthroughs/${playthroughId}/map`, { headers: authHeaders() });
    const data = await parseJsonSafe(res);
    if (!res.ok) return null;
    return data;
  } catch { return null; }
}

export const equipItem = (pid, itemId) => postAction(`/playthroughs/${pid}/equip`, { item_id: itemId });
export const unequipItem = (pid, itemId) => postAction(`/playthroughs/${pid}/unequip`, { item_id: itemId });
export const useItem = (pid, itemId) => postAction(`/playthroughs/${pid}/use`, { item_id: itemId });
export const dropItem = (pid, itemId) => postAction(`/playthroughs/${pid}/drop`, { item_id: itemId });
export const completePlaythrough = (pid) => postAction(`/playthroughs/${pid}/complete`, {});

export const compressMemory = (pid) => postAction(`/playthroughs/${pid}/compress`, {});
