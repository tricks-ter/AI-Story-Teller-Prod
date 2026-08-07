import { BASE_URL, authHeaders } from "./auth";

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
      const res = await fetch(`${BASE_URL}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(body),
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
