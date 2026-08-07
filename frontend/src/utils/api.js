const _raw = import.meta.env.VITE_API_URL;
const BASE_URL = _raw ? _raw.replace(/\/$/, "") + "/api" : "/api";

export async function checkHealth() {
  const res = await fetch(`${BASE_URL}/health`);
  if (!res.ok) throw new Error("Backend unreachable");
  return res.json();
}

async function collectClientInfo() {
  const info = {
    screen: `${window.screen.width}x${window.screen.height}`,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    language: navigator.language || "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
    platform: navigator.platform || "",
    mobile: /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent),
    touch_points: navigator.maxTouchPoints || 0,
    cores: navigator.hardwareConcurrency || null,
    memory_gb: navigator.deviceMemory || null,
  };
  try {
    const uad = navigator.userAgentData;
    if (uad && uad.getHighEntropyValues) {
      const he = await uad.getHighEntropyValues(["model", "platform", "platformVersion", "brands"]);
      info.ua_model = he.model || "";
      info.ua_platform = he.platform || "";
      info.ua_platform_version = he.platformVersion || "";
      info.ua_brands = (he.brands || []).map((b) => `${b.brand} ${b.version}`).join(", ");
    }
  } catch { /* Firefox/Safari: server falls back to UA parsing */ }
  return info;
}

export function streamChat(sessionId, messages, settings, onEvent, onError) {
  const controller = new AbortController();

  (async () => {
    const client_info = await collectClientInfo();
    if (controller.signal.aborted) return;

    const res = await fetch(`${BASE_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        messages,
        model: settings.model,
        max_tokens: settings.maxTokens,
        temperature: settings.temperature,
        enable_thinking: settings.enableThinking,
        client_info,
      }),
      signal: controller.signal,
    });

    if (!res.ok) { onError(new Error(await res.text() || "Failed")); return; }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try { onEvent(JSON.parse(raw)); } catch {}
        }
      }
    }
  })().catch((err) => { if (err.name !== "AbortError") onError(err); });

  return () => controller.abort();
}
