import { BASE_URL, authHeaders, withTelemetry, parseJsonSafe } from "./auth";

export { BASE_URL };

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

  (async () => {
    try {
      const enriched = await withTelemetry(body);
      const res = await fetch(`${BASE_URL}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(enriched),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) { onError(new Error(`HTTP ${res.status}`)); return; }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const line = chunk.trim();
          if (!line.startsWith("data:")) continue;
          try { onEvent(JSON.parse(line.slice(5).trim())); } catch {}
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") onError(err);
    }
  })();

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

  (async () => {
    try {
      const enriched = await withTelemetry(body);
      const res = await fetch(`${BASE_URL}/stories/${storyId}/continue`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(enriched),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) { onError(new Error(`HTTP ${res.status}`)); return; }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const line = chunk.trim();
          if (!line.startsWith("data:")) continue;
          try { onEvent(JSON.parse(line.slice(5).trim())); } catch {}
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") onError(err);
    }
  })();

  return () => controller.abort();
}

// ── Phase 4: Inventory / Equipment ──
export async function fetchInventory(playthroughId) {
  try {
    const res = await fetch(`${BASE_URL}/playthroughs/${playthroughId}/inventory`, { headers: authHeaders() });
    const data = await parseJsonSafe(res);
    if (!res.ok) return null;
    return data;
  } catch {
    return null;
  }
}

export async function equipItem(playthroughId, itemId) {
  try {
    const res = await fetch(`${BASE_URL}/playthroughs/${playthroughId}/equip`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ item_id: itemId }),
    });
    const data = await parseJsonSafe(res);
    if (!res.ok) return { ok: false, detail: data?.detail || `HTTP ${res.status}` };
    return { ok: true };
  } catch (err) {
    return { ok: false, detail: "Connection error" };
  }
}

export async function unequipItem(playthroughId, itemId) {
  try {
    const res = await fetch(`${BASE_URL}/playthroughs/${playthroughId}/unequip`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ item_id: itemId }),
    });
    const data = await parseJsonSafe(res);
    if (!res.ok) return { ok: false, detail: data?.detail || `HTTP ${res.status}` };
    return { ok: true };
  } catch (err) {
    return { ok: false, detail: "Connection error" };
  }
}
