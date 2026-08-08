import { useState, useEffect, useCallback, useRef } from "react";
import { Menu, X, AlertCircle, Settings2, Home } from "lucide-react";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
import SettingsPanel from "./components/SettingsPanel";
import LandingPage from "./components/LandingPage";
import StoryCreator from "./components/StoryCreator";
import AuthPage from "./components/AuthPage";
import StoryLibrary from "./components/StoryLibrary";
import { streamChat, streamStory } from "./utils/api";
import { listSessions, createSession, getMessages, appendMessage, updateSessionTitle, deleteSession, loadSettings, saveSettings } from "./utils/storage";
import { getSavedUser, getToken, fetchMe, clearAuth, authHeaders, BASE_URL, parseJsonSafe, friendlyHttp, describeNetworkError, withTelemetry } from "./utils/auth";

export default function App() {
  const [view, setView] = useState("landing");
  const [storyContext, setStoryContext] = useState(null);
  const [user, setUser] = useState(getSavedUser());
  const [pendingAction, setPendingAction] = useState(null);

  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingMsg, setStreamingMsg] = useState(null);
  const [statusText, setStatusText] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [error, setError] = useState(null);
  const [settings, setSettings] = useState(loadSettings);
  const stopRef = useRef(null);

  useEffect(() => { setSessions(listSessions()); }, []);
  useEffect(() => { saveSettings(settings); }, [settings]);

  useEffect(() => {
    if (getToken()) {
      fetchMe().then(u => { if (u) setUser(u); else { clearAuth(); setUser(null); } });
    }
  }, []);

  const refreshSessions = () => setSessions(listSessions());

  const handleSelectSession = (sessionId) => { setActiveSessionId(sessionId); setMessages(getMessages(sessionId)); setStreamingMsg(null); setStatusText(""); setError(null); setSidebarOpen(false); };
  const handleNewChat = () => { const session = createSession(); refreshSessions(); setActiveSessionId(session.session_id); setMessages([]); setStreamingMsg(null); setStatusText(""); setError(null); setSidebarOpen(false); };
  const handleDeleteSession = (sessionId) => { deleteSession(sessionId); refreshSessions(); if (activeSessionId === sessionId) { setActiveSessionId(null); setMessages([]); setStreamingMsg(null); } };
  const handleSettingsChange = (next) => setSettings(next);
  const handleToggleThinking = () => setSettings((prev) => ({ ...prev, enableThinking: !prev.enableThinking }));

  const doStartChat = () => { setView("chat"); handleNewChat(); };
  const doOpenLibrary = () => { setView("library"); };

  const requireAuth = (action) => {
    if (user) { action === "chat" ? doStartChat() : doOpenLibrary(); }
    else { setPendingAction(action); setView("auth"); }
  };

  const handleAuthed = (u) => {
    setUser(u);
    const next = pendingAction;
    setPendingAction(null);
    if (next === "chat") doStartChat();
    else if (next === "story") doOpenLibrary();
    else setView("landing");
  };

  const handleLogout = () => { clearAuth(); setUser(null); setStoryContext(null); setView("landing"); };

  const handleOpenStory = async (story) => {
    setStoryContext(story);
    setView("chat");
    const session = createSession();
    refreshSessions();
    setActiveSessionId(session.session_id);
    setStreamingMsg(null); setStatusText(""); setError(null); setSidebarOpen(false);
    setMessages([]);
    try {
      const res = await fetch(`${BASE_URL}/stories/${story.id}/messages?limit=100`, { headers: authHeaders() });
      const data = await parseJsonSafe(res);
      if (!res.ok) throw new Error(friendlyHttp(res.status, data?.detail));
      const seeded = (Array.isArray(data) ? data : []).map(m => ({
        id: `db-${m.id}`,
        role: m.role === "system" ? "assistant" : m.role,
        content: m.content,
        timestamp: m.created_at
      }));
      setMessages(seeded);
      seeded.forEach(m => appendMessage(session.session_id, m));
    } catch (err) {
      console.error("[openStory] error:", err);
      setError(describeNetworkError(err));
    }
  };

  const handleStartStory = async (storyData) => {
    try {
      const enriched = await withTelemetry(storyData);
      const res = await fetch(`${BASE_URL}/stories`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(enriched)
      });
      const data = await parseJsonSafe(res);
      if (!res.ok) throw new Error(friendlyHttp(res.status, data?.detail));
      setStoryContext({ ...storyData, id: data.story_id });
      setView("chat");
      handleNewChat();
    } catch (err) {
      console.error("Failed to create story", err);
      setError(describeNetworkError(err));
      setView("library");
    }
  };

  const sendMessage = useCallback((text) => {
    const msg = typeof text === "string" ? text.trim() : "";
    if (!msg || isStreaming) return;
    setInputValue(""); setError(null); setIsStreaming(true); setStreamingMsg(null); setStatusText("connecting…");

    let sessionId = activeSessionId;
    if (!sessionId) { const s = createSession(); sessionId = s.session_id; setActiveSessionId(sessionId); refreshSessions(); }

    const userMessage = { id: `user-${Date.now()}`, role: "user", content: msg, timestamp: new Date().toISOString() };
    appendMessage(sessionId, userMessage);
    setMessages((prev) => [...prev, userMessage]);

    if (!storyContext && getMessages(sessionId).length === 1) {
      updateSessionTitle(sessionId, msg.length > 50 ? msg.slice(0, 50) + "…" : msg);
      refreshSessions();
    }

    const snap = { ...settings };
    const assistantId = `assistant-${Date.now()}`;
    let assistantContent = "";
    let assistantThinking = "";

    let cancel;

    if (storyContext) {
      // Story mode: use streamStory
      cancel = streamStory(storyContext.id, msg, snap, (event) => {
        if (event.type === "thinking") {
          assistantThinking += event.content;
          setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: assistantContent, streamingThinking: assistantThinking, timestamp: new Date().toISOString() }));
        } else if (event.type === "content") {
          assistantContent += event.content;
          setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: assistantContent, timestamp: new Date().toISOString() }));
        } else if (event.type === "state_update") {
          // Replace bubble with clean content (tags stripped)
          const cleanContent = event.clean_content || assistantContent;
          setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: cleanContent, timestamp: new Date().toISOString() }));
          assistantContent = cleanContent;

          // Update storyContext with new state
          if (event.updates && event.updates.length > 0) {
            setStoryContext((prev) => {
              const updated = { ...prev };
              event.updates.forEach(u => {
                if (u.type === "TIME_UPDATE") {
                  updated.current_day = u.day;
                  updated.time_of_day = u.time_of_day;
                }
              });
              return updated;
            });
          }
        } else if (event.type === "error") {
          setError(event.message || "Error");
          setIsStreaming(false);
          setStreamingMsg(null);
          setStatusText("");
        } else if (event.type === "done") {
          appendMessage(sessionId, { id: assistantId, role: "assistant", content: assistantContent, thinking: assistantThinking || undefined, timestamp: new Date().toISOString() });
          setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: assistantContent, thinking: assistantThinking || undefined, timestamp: new Date().toISOString() }]);
          setStreamingMsg(null);
          setIsStreaming(false);
          setStatusText("");
        }
      }, (err) => {
        setError(err.message || "Connection error");
        setIsStreaming(false);
        setStreamingMsg(null);
        setStatusText("");
      });
    } else {
      // Quick chat mode: use streamChat
      const history = getMessages(sessionId).map((m) => ({ role: m.role, content: m.content }));
      cancel = streamChat(sessionId, history, snap, (event) => {
        if (event.type === "status") setStatusText(event.message ?? "");
        else if (event.type === "thinking") {
          assistantThinking += event.content;
          setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: assistantContent, streamingThinking: assistantThinking, timestamp: new Date().toISOString() }));
          setStatusText("");
        } else if (event.type === "content") {
          assistantContent += event.content;
          setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: assistantContent, timestamp: new Date().toISOString() }));
          setStatusText("");
        } else if (event.type === "error") {
          setError(event.message || "Error");
          setIsStreaming(false);
          setStreamingMsg(null);
          setStatusText("");
        } else if (event.type === "done") {
          appendMessage(sessionId, { id: assistantId, role: "assistant", content: assistantContent, thinking: assistantThinking || undefined, timestamp: new Date().toISOString() });
          setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: assistantContent, thinking: assistantThinking || undefined, timestamp: new Date().toISOString() }]);
          setStreamingMsg(null);
          setIsStreaming(false);
          setStatusText("");
          refreshSessions();
        }
      }, (err) => {
        setError(err.message || "Connection error");
        setIsStreaming(false);
        setStreamingMsg(null);
        setStatusText("");
      });
    }

    stopRef.current = cancel;
  }, [isStreaming, activeSessionId, settings, storyContext]);

  const handleSend = useCallback(() => sendMessage(inputValue), [inputValue, sendMessage]);
  const handleSuggestion = useCallback((text) => sendMessage(text), [sendMessage]);
  const handleStop = () => {
    if (stopRef.current) { stopRef.current(); stopRef.current = null; }
    if (streamingMsg) {
      appendMessage(activeSessionId, { ...streamingMsg, content: (streamingMsg.content || "") + " *(stopped)*", streamingThinking: undefined });
      setMessages((prev) => [...prev, { ...streamingMsg, content: (streamingMsg.content || "") + " *(stopped)*", streamingThinking: undefined }]);
    }
    setStreamingMsg(null);
    setIsStreaming(false);
    setStatusText("");
  };

  const activeTitle = sessions.find((s) => s.session_id === activeSessionId)?.title ?? "InkMind";

  if (view === "landing") return <LandingPage onSelectChat={() => requireAuth("chat")} onSelectStory={() => requireAuth("story")} user={user} onSignIn={() => { setPendingAction(null); setView("auth"); }} onLogout={handleLogout} />;
  if (view === "auth") return <AuthPage onAuthed={handleAuthed} onBack={() => setView("landing")} />;
  if (view === "library") return <StoryLibrary user={user} onOpenStory={handleOpenStory} onNewStory={() => setView("storySetup")} onBack={() => setView("landing")} />;
  if (view === "storySetup") return <StoryCreator onStart={handleStartStory} onBack={() => setView("library")} />;

  return (
    <div className="flex h-[100dvh] bg-gray-900 text-gray-100 overflow-hidden">
      {sidebarOpen && <div className="fixed inset-0 bg-black/60 z-20 md:hidden" onClick={() => setSidebarOpen(false)} />}
      {settingsOpen && <SettingsPanel settings={settings} onChange={handleSettingsChange} onClose={() => setSettingsOpen(false)} />}
      <Sidebar sessions={sessions} activeId={activeSessionId} onSelect={handleSelectSession} onCreate={handleNewChat} onDelete={handleDeleteSession} isOpen={sidebarOpen} />
      <div className="flex flex-col flex-1 min-w-0">
        <header className="flex items-center gap-2 px-3 sm:px-4 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
          <button onClick={() => setSidebarOpen((o) => !o)} className="md:hidden p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <button onClick={() => { setStoryContext(null); setView("landing"); }} className="p-2.5 rounded-xl hover:bg-gray-800 text-purple-400 hover:text-purple-300 min-w-[44px] min-h-[44px] flex items-center justify-center transition-colors touch-manipulation" title="Back to Hub">
            <Home size={18} />
          </button>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-white truncate">{storyContext ? storyContext.title : activeTitle}</h2>
            <p className="text-xs text-gray-500 truncate">
              {storyContext
                ? `Day ${storyContext.current_day ?? 1} · ${storyContext.time_of_day ?? "Morning"}${storyContext.character_name ? ` · ${storyContext.character_name}` : ""}`
                : "Advanced reasoning model"}
            </p>
          </div>
          <button onClick={() => setSettingsOpen(true)} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 hover:text-white min-w-[44px] min-h-[44px] flex items-center justify-center transition-colors touch-manipulation" title="Settings">
            <Settings2 size={18} />
          </button>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-xs text-gray-400 hidden sm:inline">Online</span>
          </div>
        </header>
        {error && (
          <div className="flex items-center gap-2 px-4 py-3 bg-red-500/10 border-b border-red-500/20 text-red-400 text-sm animate-fade-in flex-shrink-0">
            <AlertCircle size={15} className="flex-shrink-0" />
            <span className="flex-1 text-[13px] sm:text-sm">{error}</span>
            <button onClick={() => setError(null)} className="p-1.5 text-red-500 hover:text-red-300 touch-manipulation"><X size={14} /></button>
          </div>
        )}
        <ChatWindow messages={messages} streamingMsg={streamingMsg} isStreaming={isStreaming} statusText={statusText} onSuggestion={handleSuggestion} />
        <ChatInput value={inputValue} onChange={setInputValue} onSend={handleSend} onStop={handleStop} onOpenSettings={() => setSettingsOpen(true)} onToggleThinking={handleToggleThinking} isStreaming={isStreaming} disabled={false} settings={settings} />
      </div>
    </div>
  );
}
