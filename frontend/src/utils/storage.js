import { DEFAULT_MODEL_ID } from "./models";
// ─── Chat history ───────────────────────────────────────────────────────────

const CHAT_KEY = "glm_chat_data";

function loadChats() {
  try {
    const raw = localStorage.getItem(CHAT_KEY);
    return raw ? JSON.parse(raw) : { sessions: {} };
  } catch {
    return { sessions: {} };
  }
}

function persistChats(data) {
  try {
    localStorage.setItem(CHAT_KEY, JSON.stringify(data));
  } catch {
    // localStorage full or unavailable
  }
}

export function listSessions() {
  const { sessions } = loadChats();
  return Object.values(sessions).sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  );
}

export function createSession() {
  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  const session = {
    session_id: id,
    created_at: now,
    title: "New Chat",
    messages: [],
  };
  const data = loadChats();
  data.sessions[id] = session;
  persistChats(data);
  return session;
}

export function getMessages(sessionId) {
  return loadChats().sessions[sessionId]?.messages ?? [];
}

export function appendMessage(sessionId, message) {
  const data = loadChats();
  if (!data.sessions[sessionId]) return;
  data.sessions[sessionId].messages.push(message);
  persistChats(data);
}

export function updateSessionTitle(sessionId, title) {
  const data = loadChats();
  if (!data.sessions[sessionId]) return;
  data.sessions[sessionId].title = title;
  persistChats(data);
}

export function deleteSession(sessionId) {
  const data = loadChats();
  delete data.sessions[sessionId];
  persistChats(data);
}

// ─── User settings ───────────────────────────────────────────────────────────

const SETTINGS_KEY = "glm_chat_settings";

export const DEFAULT_SETTINGS = {
  model: DEFAULT_MODEL_ID,
  maxTokens: 4096,
  temperature: 0.7,
  enableThinking: true,
};

export function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveSettings(settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // ignore
  }
}
