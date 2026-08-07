// frontend/src/App.jsx
import { useState, useEffect, useCallback, useRef } from "react";
import { Menu, X, AlertCircle, Settings2 } from "lucide-react";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
import SettingsPanel from "./components/SettingsPanel";
import { streamChat } from "./utils/api";
import { listSessions, createSession, getMessages, appendMessage, updateSessionTitle, deleteSession, loadSettings, saveSettings } from "./utils/storage";

export default function App() {
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
  const refreshSessions = () => setSessions(listSessions());

  const handleSelectSession = (sessionId) => { setActiveSessionId(sessionId); setMessages(getMessages(sessionId)); setStreamingMsg(null); setStatusText(""); setError(null); setSidebarOpen(false); };
  const handleNewChat = () => { const session = createSession(); refreshSessions(); setActiveSessionId(session.session_id); setMessages([]); setStreamingMsg(null); setStatusText(""); setError(null); setSidebarOpen(false); };
  const handleDeleteSession = (sessionId) => { deleteSession(sessionId); refreshSessions(); if (activeSessionId === sessionId) { setActiveSessionId(null); setMessages([]); setStreamingMsg(null); } };
  const handleSettingsChange = (next) => setSettings(next);
  
  // FIX: Added missing arrow (=>)
  const handleToggleThinking = () =>
    setSettings((prev) => ({ ...prev, enableThinking: !prev.enableThinking }));

  const sendMessage = useCallback((text) => {
    const msg = typeof text === "string" ? text.trim() : "";
    if (!msg || isStreaming) return;
    setInputValue(""); setError(null); setIsStreaming(true); setStreamingMsg(null); setStatusText("connecting…");
    let sessionId = activeSessionId;
    if (!sessionId) { const s = createSession(); sessionId = s.session_id; setActiveSessionId(sessionId); refreshSessions(); }
    const userMessage = { id: `user-${Date.now()}`, role: "user", content: msg, timestamp: new Date().toISOString() };
    appendMessage(sessionId, userMessage); setMessages((prev) => [...prev, userMessage]);
    if (getMessages(sessionId).length === 1) { updateSessionTitle(sessionId, msg.length > 50 ? msg.slice(0, 50) + "…" : msg); refreshSessions(); }
    const history = getMessages(sessionId).map((m) => ({ role: m.role, content: m.content }));
    const assistantId = `assistant-${Date.now()}`;
    let assistantContent = ""; let assistantThinking = "";
    const snap = { ...settings };

    // FIX: Added sessionId as first argument
    const cancel = streamChat(sessionId, history, snap, (event) => {
      if (event.type === "status") setStatusText(event.message ?? "");
      else if (event.type === "thinking") { assistantThinking += event.content; setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: assistantContent, streamingThinking: assistantThinking, timestamp: new Date().toISOString() })); setStatusText(""); }
      else if (event.type === "content") { assistantContent += event.content; setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: assistantContent, timestamp: new Date().toISOString() })); setStatusText(""); }
      else if (event.type === "error") { setError(event.message || "Error"); setIsStreaming(false); setStreamingMsg(null); setStatusText(""); }
      else if (event.type === "done") { appendMessage(sessionId, { id: assistantId, role: "assistant", content: assistantContent, thinking: assistantThinking || undefined, timestamp: new Date().toISOString() }); setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: assistantContent, thinking: assistantThinking || undefined, timestamp: new Date().toISOString() }]); setStreamingMsg(null); setIsStreaming(false); setStatusText(""); refreshSessions(); }
    }, (err) => { setError(err.message || "Connection error"); setIsStreaming(false); setStreamingMsg(null); setStatusText(""); });
    stopRef.current = cancel;
  }, [isStreaming, activeSessionId, settings]);

  const handleSend = useCallback(() => sendMessage(inputValue), [inputValue, sendMessage]);
  const handleSuggestion = useCallback((text) => sendMessage(text), [sendMessage]);
  const handleStop = () => { if (stopRef.current) { stopRef.current(); stopRef.current = null; } if (streamingMsg) { appendMessage(activeSessionId, { ...streamingMsg, content: (streamingMsg.content || "") + " *(stopped)*", streamingThinking: undefined }); setMessages((prev) => [...prev, { ...streamingMsg, content: (streamingMsg.content || "") + " *(stopped)*", streamingThinking: undefined }]); } setStreamingMsg(null); setIsStreaming(false); setStatusText(""); };
  const activeTitle = sessions.find((s) => s.session_id === activeSessionId)?.title ?? "InkMind";

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
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-white truncate">{activeTitle}</h2>
            <p className="text-xs text-gray-500 hidden sm:block">Advanced reasoning model</p>
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
