import React, { useState, useEffect, useCallback, useRef } from "react";
import { Menu, X, AlertCircle, Settings2, Home, Info, Flag, Trophy } from "lucide-react";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
import SettingsPanel from "./components/SettingsPanel";
import LandingPage from "./components/LandingPage";
import StoryCreator from "./components/StoryCreator";
import AuthPage from "./components/AuthPage";
import StoryLibrary from "./components/StoryLibrary";
import { streamChat, streamStory, completePlaythrough } from "./utils/api";
import { listSessions, createSession, getMessages, appendMessage, updateSessionTitle, deleteSession, loadSettings, saveSettings } from "./utils/storage";
import { getSavedUser, getToken, fetchMe, clearAuth, authHeaders, BASE_URL, parseJsonSafe, friendlyHttp, describeNetworkError, withTelemetry } from "./utils/auth";

export default function App() {
  const [user, setUser] = useState(getSavedUser());
  const [view, setView] = useState("landing");
  const [pendingAction, setPendingAction] = useState(null);
  const [authMsg, setAuthMsg] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState(loadSettings());
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [streamingMsg, setStreamingMsg] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [storyContext, setStoryContext] = useState(null);
  const stopRef = useRef(null);
  const scrollRef = useRef(null);

  const requireAuth = useCallback((action) => {
    if (!user) { setPendingAction(action); setView("auth"); return false; }
    return true;
  }, [user]);

  const handleAuthed = useCallback((u) => {
    setUser(u);
    setView("landing");
    if (pendingAction === "chat") handleNewChat();
    else if (pendingAction === "story") setView("storySetup");
    setPendingAction(null);
  }, [pendingAction]);

  const handleLogout = useCallback(() => {
    clearAuth();
    setUser(null);
    setSessions([]);
    setMessages([]);
    setStoryContext(null);
    setView("landing");
  }, []);

  const handleStartStory = useCallback(async (storyData) => {
    if (!requireAuth("story")) return;
    try {
      const res = await fetch(`${BASE_URL}/stories`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(withTelemetry(storyData))
      });
      if (!res.ok) throw new Error(await parseJsonSafe(res));
      const data = await res.json();
      
      const pRes = await fetch(`${BASE_URL}/stories/${data.story_id}/play`, {
        method: "POST",
        headers: authHeaders()
      });
      const pData = await pRes.json();
      
      const newSessionId = createSession("Story: " + storyData.title);
      setSessions(prev => [{ session_id: newSessionId, title: "Story: " + storyData.title, created_at: new Date().toISOString(), messages: [] }, ...prev]);
      setActiveSessionId(newSessionId);
      setStoryContext({ ...pData, story_id: data.story_id, currency: pData.playthrough?.currency || 0 });
      
      const introRes = await fetch(`${BASE_URL}/stories/${data.story_id}/messages?base_only=true`, { headers: authHeaders() });
      if (introRes.ok) {
        const introData = await introRes.json();
        setMessages(introData.map(m => ({ role: m.role, content: m.content, type: m.message_type })));
      }
      setView("chat");
    } catch (err) {
      setAuthMsg("Could not start story. " + (err.message || ""));
    }
  }, [requireAuth]);

  const handleOpenStory = useCallback(async (story) => {
    if (!requireAuth("story")) return;
    try {
      const pRes = await fetch(`${BASE_URL}/stories/${story.id}/play`, {
        method: "POST",
        headers: authHeaders()
      });
      const pData = await pRes.json();
      
      const newSessionId = createSession("Story: " + story.title);
      setSessions(prev => [{ session_id: newSessionId, title: "Story: " + story.title, created_at: new Date().toISOString(), messages: [] }, ...prev]);
      setActiveSessionId(newSessionId);
      setStoryContext({ ...pData, story_id: story.id, currency: pData.playthrough?.currency || 0 });
      
      const introRes = await fetch(`${BASE_URL}/stories/${story.id}/messages?base_only=true`, { headers: authHeaders() });
      if (introRes.ok) {
        const introData = await introRes.json();
        setMessages(introData.map(m => ({ role: m.role, content: m.content, type: m.message_type })));
      }
      setView("chat");
    } catch (err) {
      setAuthMsg("Could not open story. " + (err.message || ""));
    }
  }, [requireAuth]);

  const handleNewChat = useCallback(() => {
    if (!requireAuth("chat")) return;
    const newId = createSession("New Chat");
    setSessions(prev => [{ session_id: newId, title: "New Chat", created_at: new Date().toISOString(), messages: [] }, ...prev]);
    setActiveSessionId(newId);
    setMessages([]);
    setStoryContext(null);
    setView("chat");
    setSidebarOpen(false);
  }, [requireAuth]);

  const handleSelectSession = useCallback((id) => {
    setActiveSessionId(id);
    setMessages(getMessages(id));
    setStoryContext(null);
    setView("chat");
    setSidebarOpen(false);
  }, []);

  const handleDeleteSession = useCallback((id) => {
    deleteSession(id);
    setSessions(prev => prev.filter(s => s.session_id !== id));
    if (activeSessionId === id) {
      setActiveSessionId(null);
      setMessages([]);
      setView("landing");
    }
  }, [activeSessionId]);

  const handleSettingsChange = useCallback((newSettings) => {
    setSettings(newSettings);
    saveSettings(newSettings);
  }, []);

  const handleSuggestion = useCallback((text) => {
    setInputValue(text);
  }, []);

  const handleToggleThinking = useCallback(() => {
    setSettings(prev => {
      const next = { ...prev, enableThinking: !prev.enableThinking };
      saveSettings(next);
      return next;
    });
  }, []);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text || isStreaming) return;

    if (storyContext) {
      if (!storyContext.playthrough_id) return;
      setInputValue("");
      setIsStreaming(true);
      setStreamingMsg({ role: "assistant", content: "" });
      setStatusText("Thinking...");

      stopRef.current = streamStory(
        storyContext.story_id,
        text,
        settings,
        (ev) => {
          if (ev.type === "thinking") setStatusText("Thinking...");
          else if (ev.type === "content") {
            setStreamingMsg(prev => prev ? { ...prev, content: prev.content + ev.content } : { role: "assistant", content: ev.content });
            setStatusText("Writing...");
          }
          else if (ev.type === "state_update") {
            const finalMsg = { role: "assistant", content: ev.clean_content };
            setMessages(prev => {
              const next = [...prev, { role: "user", content: text }, finalMsg];
              appendMessage(activeSessionId, finalMsg);
              updateSessionTitle(activeSessionId, "Story: " + (storyContext.story?.title || text.slice(0, 20)));
              return next;
            });
            setStreamingMsg(null);
            
            setStoryContext(prev => {
              const next = { ...prev };
              if (ev.day) next.current_day = ev.day;
              if (ev.time_of_day) next.time_of_day = ev.time_of_day;
              if (ev.status) next.status = ev.status;
              if (ev.currency !== undefined) next.currency = ev.currency;
              
              if (Array.isArray(ev.updates)) {
                 ev.updates.forEach(u => {
                   if (u.type === "LOCATION_UPDATE" && u.location) {
                     next.current_location = u.location;
                   }
                   if (u.type === "STAT_UPDATE" && u.character && u.stat && u.value !== undefined && !u.is_delta) {
                     const c = next.characters?.find(ch => ch.character_name.toLowerCase() === u.character.toLowerCase());
                     if (c) {
                       if (!c.metadata) c.metadata = {};
                       if (!c.metadata.stats) c.metadata.stats = {};
                       c.metadata.stats[u.stat] = u.value;
                     }
                   }
                   if (u.type === "CURRENCY_UPDATE" && u.amount !== undefined && !u.is_delta) {
                     next.currency = u.amount;
                   }
                 });
              }
              return next;
            });
            setStatusText("");
          }
          else if (ev.type === "error") {
            setMessages(prev => {
              const next = [...prev, { role: "user", content: text }, { role: "system", content: ev.message, type: "error" }];
              return next;
            });
            setStreamingMsg(null);
            setStatusText("");
          }
          else if (ev.type === "done") {
            setIsStreaming(false);
            setStreamingMsg(null);
            setStatusText("");
          }
        },
        (err) => {
          setMessages(prev => [...prev, { role: "user", content: text }, { role: "system", content: err.message, type: "error" }]);
          setIsStreaming(false);
          setStreamingMsg(null);
          setStatusText("");
        }
      );
    } else {
      if (!activeSessionId) return;
      setInputValue("");
      const userMsg = { role: "user", content: text };
      setMessages(prev => [...prev, userMsg]);
      appendMessage(activeSessionId, userMsg);
      updateSessionTitle(activeSessionId, text.slice(0, 30));
      setIsStreaming(true);
      setStreamingMsg({ role: "assistant", content: "" });
      setStatusText("Thinking...");

      stopRef.current = streamChat(
        activeSessionId,
        [...messages, userMsg].map(m => ({ role: m.role, content: m.content })),
        settings,
        (ev) => {
          if (ev.type === "thinking") setStatusText("Thinking...");
          else if (ev.type === "content") {
            setStreamingMsg(prev => prev ? { ...prev, content: prev.content + ev.content } : { role: "assistant", content: ev.content });
            setStatusText("Writing...");
          }
          else if (ev.type === "done") {
            setIsStreaming(false);
            setStreamingMsg(null);
            setStatusText("");
          }
        },
        (err) => {
          setIsStreaming(false);
          setStreamingMsg(null);
          setStatusText("");
        }
      );
    }
  }, [inputValue, isStreaming, storyContext, activeSessionId, messages, settings]);

  const handleStop = useCallback(() => {
    if (stopRef.current) stopRef.current();
    if (streamingMsg && streamingMsg.content) {
      setMessages(prev => [...prev, streamingMsg]);
      if (!storyContext) appendMessage(activeSessionId, streamingMsg);
    }
    setIsStreaming(false);
    setStreamingMsg(null);
    setStatusText("");
  }, [streamingMsg, storyContext, activeSessionId]);

  useEffect(() => {
    const t = getToken();
    if (t) {
      fetchMe().then(u => {
        if (u) setUser(u);
        else { clearAuth(); setUser(null); }
      }).catch(() => { clearAuth(); setUser(null); });
    }
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingMsg]);

  const activeTitle = sessions.find((s) => s.session_id === activeSessionId)?.title ?? "InkMind";
  const storyCompleted = storyContext?.status === "completed";

  if (view === "landing") return <LandingPage onSelectChat={() => requireAuth("chat")} onSelectStory={() => requireAuth("story")} user={user} onSignIn={() => { setPendingAction(null); setView("auth"); }} onLogout={handleLogout} />;
  if (view === "auth") return <AuthPage onAuthed={handleAuthed} onBack={() => setView("landing")} />;
  if (view === "library") return <StoryLibrary user={user} onOpenStory={handleOpenStory} onNewStory={() => setView("storySetup")} onBack={() => setView("landing")} />;
  if (view === "storySetup") return <StoryCreator onStart={handleStartStory} onBack={() => setView("library")} />;

  return (
    <div className="flex h-[100dvh] bg-gray-900 text-gray-100 overflow-hidden">
      {sidebarOpen && <div className="fixed inset-0 bg-black/60 z-20 md:hidden" onClick={() => setSidebarOpen(false)} />}
      {settingsOpen && <SettingsPanel settings={settings} onChange={handleSettingsChange} onClose={() => setSettingsOpen(false)} />}
      <Sidebar sessions={sessions} activeId={activeSessionId} onSelect={handleSelectSession} onCreate={handleNewChat} onDelete={handleDeleteSession} isOpen={sidebarOpen} storyContext={storyContext} />
      <div className="flex flex-col flex-1 min-w-0">
        <header className="flex items-center gap-2 px-3 sm:px-4 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="md:hidden p-2 rounded-xl hover:bg-gray-800 touch-manipulation">
            <Menu size={20} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-sm sm:text-base font-semibold truncate">{activeTitle}</h1>
            {storyContext && (
              <p className="text-[10px] text-gray-500 truncate">
                Day {storyContext.current_day} · {storyContext.time_of_day} · {storyContext.status}
              </p>
            )}
          </div>
          {!storyContext && user && (
            <button onClick={() => setView("library")} className="p-2 rounded-xl hover:bg-gray-800 touch-manipulation" title="Story Library">
              <Trophy size={18} className="text-amber-400" />
            </button>
          )}
          {storyContext && !storyCompleted && (
            <button onClick={async () => { if(confirm("End this saga?")) { await completePlaythrough(storyContext.playthrough_id); setStoryContext(prev => ({...prev, status: "completed"})); }}} className="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-medium touch-manipulation">
              End Saga
            </button>
          )}
          {user && (
            <button onClick={handleLogout} className="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-medium touch-manipulation">
              Logout
            </button>
          )}
        </header>
        <ChatWindow messages={messages} streamingMsg={streamingMsg} isStreaming={isStreaming} statusText={statusText} onSuggestion={handleSuggestion} isStory={!!storyContext} scrollRef={scrollRef} />
        <ChatInput value={inputValue} onChange={setInputValue} onSend={handleSend} onStop={handleStop} onOpenSettings={() => setSettingsOpen(true)} onToggleThinking={handleToggleThinking} isStreaming={isStreaming || storyCompleted} disabled={isStreaming || storyCompleted} settings={settings} />
      </div>
    </div>
  );
}
