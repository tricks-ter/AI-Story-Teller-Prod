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
import StoryDetails from "./components/StoryDetails";
import HUD from "./components/HUD";
import { streamChat, streamStory, completePlaythrough } from "./utils/api";
import { listSessions, createSession, getMessages, appendMessage, updateSessionTitle, deleteSession, loadSettings, saveSettings } from "./utils/storage";
import { getSavedUser, getToken, fetchMe, clearAuth, authHeaders, BASE_URL, parseJsonSafe, friendlyHttp, describeNetworkError, withTelemetry } from "./utils/auth";
import { getLocalUser, saveLocalUser, getLocalStory, saveLocalStory, getLocalPlaythrough, saveLocalPlaythrough, getLocalMessages, saveLocalMessages, clearLocalDB, clearHudCache } from "./utils/localDb";
import { applyStateUpdateToCache, getCachedStoryContext, cacheInventory } from "./utils/hudStore";
import { syncQueue } from "./utils/syncQueue";

export default function App() {
  const [view, setView] = useState("landing");
  const [storyContext, setStoryContext] = useState(null);
  const [user, setUser] = useState(getSavedUser());
  const [pendingAction, setPendingAction] = useState(null);
  const [detailsStory, setDetailsStory] = useState(null);

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
  const [notice, setNotice] = useState(null);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [settings, setSettings] = useState(loadSettings);
  const [editingStory, setEditingStory] = useState(null);
  const stopRef = useRef(null);

  useEffect(() => { setSessions(listSessions()); }, []);
  useEffect(() => { saveSettings(settings); }, [settings]);
  useEffect(() => { fetch(`${BASE_URL}/health`).catch(() => {}); }, []);
  
  useEffect(() => {
    if (getToken()) {
      getLocalUser().then(localU => { if (localU && !user) setUser(localU); });

      fetchMe().then(u => { 
        if (u) {
          setUser(u); 
          saveLocalUser(u);
          syncQueue.enqueue('SYNC_LIBRARY', { userId: u.id });
        } else { 
          clearAuth(); 
          setUser(null); 
        } 
      });
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
    saveLocalUser(u);
    const next = pendingAction;
    setPendingAction(null);
    if (next === "chat") doStartChat();
    else if (next === "story") doOpenLibrary();
    else setView("landing");
  };

  const handleLogout = () => {
    fetch(`${BASE_URL}/auth/logout`, { method: "POST", headers: authHeaders() }).catch(() => {});
    clearAuth(); setUser(null); setStoryContext(null); setView("landing");
    clearLocalDB().catch(() => {});
  };

  const handleEndJourney = async () => {
    if (!storyContext?.playthrough_id) return;
    if (!confirmEnd) {
      setConfirmEnd(true);
      setTimeout(() => setConfirmEnd(false), 3000);
      return;
    }
    setConfirmEnd(false);
    const res = await completePlaythrough(storyContext.playthrough_id);
    if (res.ok) {
      setStoryContext(prev => ({ ...prev, status: "completed" }));
      setNotice("🏁 Saga completed — well played!");
    } else {
      setError(res.detail || "Could not complete the saga.");
    }
  };

  // Library click -> detail review (no longer jumps straight to chat)
  const handleOpenStory = (story) => {
    setDetailsStory(story);
    setView("details");
  };

  // From detail page: user tapped Continue/New Journey -> enter the saga
  const handleStartJourney = async (story) => {
    setStoryContext(story);
    setView("chat");
    const session = createSession();
    refreshSessions();
    setActiveSessionId(session.session_id);
    setStreamingMsg(null); setStatusText(""); setError(null); setNotice(null); setSidebarOpen(false);
    setMessages([]);

    try {
      const playRes = await fetch(`${BASE_URL}/stories/${story.id}/play`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(await withTelemetry({}))
      });
      const playData = await parseJsonSafe(playRes);
      if (!playRes.ok) throw new Error(friendlyHttp(playRes.status, playData?.detail));
      const pt = playData.playthrough;

      const finalContext = {
        ...story,
        playthrough_id: pt.id,
        current_day: pt.current_day,
        time_of_day: pt.time_of_day,
        status: pt.status,
        characters: playData.characters || [],
        current_location: pt.metadata?.current_location || "Unknown Realm",
      };
      setStoryContext(finalContext);

      if (playData.story) await saveLocalStory(playData.story);
      await saveLocalPlaythrough(pt);
      await applyStateUpdateToCache(pt.id, finalContext);

      const msgRes = await fetch(`${BASE_URL}/playthroughs/${pt.id}/messages?limit=100`, { headers: authHeaders() });
      let msgData = await parseJsonSafe(msgRes);
      if (!msgRes.ok) throw new Error(friendlyHttp(msgRes.status, msgData?.detail));

      let seeded = (Array.isArray(msgData) ? msgData : []);
      if (seeded.length === 0) {
        const baseMsgRes = await fetch(`${BASE_URL}/stories/${story.id}/messages?limit=50&base_only=true`, { headers: authHeaders() });
        const baseMsgData = await parseJsonSafe(baseMsgRes);
        if (baseMsgRes.ok && Array.isArray(baseMsgData) && baseMsgData.length > 0) seeded = baseMsgData;
      }

      const mapped = seeded.map(m => ({
        id: `db-${m.id}`,
        role: m.role === "system" ? "assistant" : m.role,
        content: m.content,
        timestamp: m.created_at,
        narrative: true
      }));
      
      setMessages(mapped);
      mapped.forEach(m => appendMessage(session.session_id, m));
      if (mapped.length > 0) await saveLocalMessages(pt.id, mapped, true);

      if (pt.id) {
        syncQueue.enqueue('SYNC_HUD', { ptId: pt.id, key: 'inventory' }, 'high');
        syncQueue.enqueue('SYNC_HUD', { ptId: pt.id, key: 'map' }, 'high');
        syncQueue.enqueue('SYNC_HUD', { ptId: pt.id, key: 'world' }, 'normal');
        syncQueue.enqueue('COMPRESS_MEMORY', { ptId: pt.id }, 'normal');
      }

    } catch (err) {
      console.error("[startJourney] error:", err);
      setStoryContext(null);
      setMessages([]);
      setView("details");
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
      setDetailsStory({ ...storyData, id: data.story_id });
      setView("details");
    } catch (err) {
      console.error("Failed to create story", err);
      setError(describeNetworkError(err));
      setView("library");
    }
  };

  const handleUpdateStory = async (storyId, storyData) => {
    try {
      const enriched = await withTelemetry({
        title: storyData.title,
        genre: storyData.genre,
        premise: storyData.premise,
      });
      const res = await fetch(`${BASE_URL}/stories/${storyId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(enriched)
      });
      const data = await parseJsonSafe(res);
      if (!res.ok) throw new Error(friendlyHttp(res.status, data?.detail));
      setEditingStory(null);
      // Refresh detail page with updated data
      setDetailsStory(prev => prev && prev.id === storyId ? { ...prev, ...storyData } : prev);
      setView("details");
    } catch (err) {
      console.error("Failed to update story", err);
      setError(describeNetworkError(err));
      setEditingStory(null);
      setView("details");
    }
  };

  const sendMessage = useCallback((text) => {
    const msg = typeof text === "string" ? text.trim() : "";
    if (!msg || isStreaming) return;
    if (storyContext?.status === "completed") return;
    setInputValue(""); setError(null); setIsStreaming(true); setStreamingMsg(null); setStatusText("connecting…");

    let sessionId = activeSessionId;
    if (!sessionId) { const s = createSession(); sessionId = s.session_id; setActiveSessionId(sessionId); refreshSessions(); }

    const isStory = !!storyContext;
    const userMessage = { id: `user-${Date.now()}`, role: "user", content: msg, timestamp: new Date().toISOString(), narrative: isStory };
    appendMessage(sessionId, userMessage);
    setMessages((prev) => [...prev, userMessage]);

    if (!isStory && getMessages(sessionId).length === 1) {
      updateSessionTitle(sessionId, msg.length > 50 ? msg.slice(0, 50) + "…" : msg);
      refreshSessions();
    }

    const snap = { ...settings };
    const assistantId = `assistant-${Date.now()}`;
    let assistantContent = "";
    let assistantThinking = "";

    let cancel;

    if (isStory) {
      cancel = streamStory(storyContext.id, msg, snap, (event) => {
        if (event.type === "status") {
          setStatusText(event.message ?? "");
        } else if (event.type === "thinking") {
          assistantThinking += event.content;
          setStatusText("");
          setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: assistantContent, narrative: true, timestamp: new Date().toISOString() }));
        } else if (event.type === "content") {
          assistantContent += event.content;
          setStatusText("");
          setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: assistantContent, narrative: true, timestamp: new Date().toISOString() }));
        } else if (event.type === "state_update") {
          const cleanContent = event.clean_content || assistantContent;
          assistantContent = cleanContent;
          setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: cleanContent, narrative: true, timestamp: new Date().toISOString() }));

          if (Array.isArray(event.rejected) && event.rejected.length) {
            const texts = event.rejected.map(r => {
              const label = r.item || r.ability || "Update";
              const why = (r.reason || "rejected").replace(/_/g, " ");
              return `${label} left behind (${why})`;
            });
            setNotice("🎒 " + texts.join(" · "));
          }

          setStoryContext((prev) => {
            let newContext = {
              ...prev,
              current_day: event.day ?? prev.current_day,
              time_of_day: event.time_of_day ?? prev.time_of_day,
              status: event.status ?? prev.status,
            };
            let newChars = [...(prev.characters || [])];
            for (const up of event.updates || []) {
              if (up.type === "LOCATION_UPDATE") {
                newContext.current_location = up.location;
              } else if (up.type === "STAT_UPDATE") {
                const charIdx = newChars.findIndex(c => c.character_name.toLowerCase() === up.character.toLowerCase());
                if (charIdx !== -1) {
                  const c = newChars[charIdx];
                  const meta = { ...(c.metadata || {}) };
                  const stats = { ...(meta.stats || {}) };
                  stats[up.stat] = up.value;
                  meta.stats = stats;
                  newChars[charIdx] = { ...c, metadata: meta };
                }
              } else if (up.type === "ITEM_UPDATE") {
                const charIdx = newChars.findIndex(c => c.character_name.toLowerCase() === up.character.toLowerCase());
                if (charIdx !== -1) {
                  const c = newChars[charIdx];
                  const meta = { ...(c.metadata || {}) };
                  let inv = Array.isArray(meta.inventory) ? [...meta.inventory] : [];
                  if (up.add) { if (!inv.includes(up.item)) inv.push(up.item); }
                  else { inv = inv.filter(i => String(i).toLowerCase() !== String(up.item || "").toLowerCase()); }
                  meta.inventory = inv;
                  newChars[charIdx] = { ...c, metadata: meta };
                }
              } else if (up.type === "ABILITY_UPDATE") {
                const charIdx = newChars.findIndex(c => c.character_name.toLowerCase() === up.character.toLowerCase());
                if (charIdx !== -1) {
                  const c = newChars[charIdx];
                  const meta = { ...(c.metadata || {}) };
                  let ab = Array.isArray(meta.abilities) ? [...meta.abilities] : [];
                  if (up.add) {
                    const idx = ab.findIndex(a => a && a.name && a.name.toLowerCase() === (up.ability || "").toLowerCase());
                    if (idx !== -1) { if (up.description) ab[idx] = { ...ab[idx], description: up.description }; }
                    else ab.push({ name: up.ability, description: up.description || "" });
                  } else {
                    ab = ab.filter(a => !(a && a.name && a.name.toLowerCase() === (up.ability || "").toLowerCase()));
                  }
                  meta.abilities = ab;
                  newChars[charIdx] = { ...c, metadata: meta };
                }
              }
            }
            newContext.characters = newChars;
            
            if (newContext.playthrough_id) {
              applyStateUpdateToCache(newContext.playthrough_id, newContext);
              syncQueue.enqueue('SYNC_HUD', { ptId: newContext.playthrough_id, key: 'inventory' }, 'normal');
              syncQueue.enqueue('SYNC_HUD', { ptId: newContext.playthrough_id, key: 'world' }, 'normal');
            }
            
            return newContext;
          });
        } else if (event.type === "error") {
          setError(event.message || "Error"); setIsStreaming(false); setStreamingMsg(null); setStatusText("");
        } else if (event.type === "done") {
          const finalMsg = { id: assistantId, role: "assistant", content: assistantContent, narrative: true, timestamp: new Date().toISOString() };
          appendMessage(sessionId, finalMsg);
          setMessages((prev) => [...prev, finalMsg]);
          setStreamingMsg(null); setIsStreaming(false); setStatusText("");
          if (storyContext?.playthrough_id) {
            syncQueue.enqueue('COMPRESS_MEMORY', { ptId: storyContext.playthrough_id }, 'normal');
          }
        }
      }, (err) => { setError(err.message || "Connection error"); setIsStreaming(false); setStreamingMsg(null); setStatusText(""); });
    } else {
      const history = getMessages(sessionId).map((m) => ({ role: m.role, content: m.content }));
      cancel = streamChat(sessionId, history, snap, (event) => {
        if (event.type === "status") setStatusText(event.message ?? "");
        else if (event.type === "thinking") { assistantThinking += event.content; setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: assistantContent, streamingThinking: assistantThinking, timestamp: new Date().toISOString() })); setStatusText(""); }
        else if (event.type === "content") { assistantContent += event.content; setStreamingMsg((prev) => ({ ...(prev ?? {}), id: assistantId, role: "assistant", content: assistantContent, timestamp: new Date().toISOString() })); setStatusText(""); }
        else if (event.type === "error") { setError(event.message || "Error"); setIsStreaming(false); setStreamingMsg(null); setStatusText(""); }
        else if (event.type === "done") { appendMessage(sessionId, { id: assistantId, role: "assistant", content: assistantContent, thinking: assistantThinking || undefined, timestamp: new Date().toISOString() }); setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: assistantContent, thinking: assistantThinking || undefined, timestamp: new Date().toISOString() }]); setStreamingMsg(null); setIsStreaming(false); setStatusText(""); refreshSessions(); }
      }, (err) => { setError(err.message || "Connection error"); setIsStreaming(false); setStreamingMsg(null); setStatusText(""); });
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
    setStreamingMsg(null); setIsStreaming(false); setStatusText("");
  };

  const activeTitle = sessions.find((s) => s.session_id === activeSessionId)?.title ?? "InkMind";
  const storyCompleted = storyContext?.status === "completed";

  if (view === "landing") return <LandingPage onSelectChat={() => requireAuth("chat")} onSelectStory={() => requireAuth("story")} user={user} onSignIn={() => { setPendingAction(null); setView("auth"); }} onLogout={handleLogout} />;
  if (view === "auth") return <AuthPage onAuthed={handleAuthed} onBack={() => setView("landing")} />;
  if (view === "library") return <StoryLibrary user={user} onOpenStory={handleOpenStory} onNewStory={() => setView("storySetup")} onBack={() => setView("landing")} />;
  if (view === "details") return <StoryDetails story={detailsStory} user={user} onBack={() => { setDetailsStory(null); setView("library"); }} onStartJourney={handleStartJourney} onEdit={(s) => { setEditingStory(s); setView("storyEdit"); }} />;
  if (view === "storySetup") return <StoryCreator onStart={handleStartStory} onBack={() => setView("library")} />;
  if (view === "storyEdit") return <StoryCreator initialData={editingStory} isEditing={true} onUpdate={handleUpdateStory} onBack={() => { setEditingStory(null); setView("details"); }} />;

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
          {storyContext && !storyCompleted && (
            <button onClick={handleEndJourney} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 hover:text-red-400 min-w-[44px] min-h-[44px] flex items-center justify-center transition-colors touch-manipulation" title="End journey">
              {confirmEnd ? <span className="text-[10px] font-bold text-red-400 px-0.5">Sure?</span> : <Flag size={18} />}
            </button>
          )}
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
        {notice && (
          <div className="flex items-center gap-2 px-4 py-2.5 bg-amber-500/10 border-b border-amber-500/20 text-amber-300 text-sm animate-fade-in flex-shrink-0">
            <Info size={15} className="flex-shrink-0" />
            <span className="flex-1 text-[12px] sm:text-sm">{notice}</span>
            <button onClick={() => setNotice(null)} className="p-1.5 text-amber-500 hover:text-amber-300 touch-manipulation"><X size={14} /></button>
          </div>
        )}
        {storyCompleted && (
          <div className="flex items-center gap-2 px-4 py-3 bg-purple-500/10 border-b border-purple-500/20 text-purple-300 text-sm flex-shrink-0">
            <Trophy size={15} className="flex-shrink-0" />
            <span className="flex-1 text-[13px] sm:text-sm">This saga is complete.</span>
            <button onClick={() => handleStartJourney(storyContext)} className="px-3 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold min-h-[44px] touch-manipulation active:scale-95">
              Start New Journey
            </button>
          </div>
        )}
        {storyContext && <HUD storyContext={storyContext} />}
        <ChatWindow messages={messages} streamingMsg={streamingMsg} isStreaming={isStreaming} statusText={statusText} onSuggestion={handleSuggestion} isStory={!!storyContext} />
        <ChatInput value={inputValue} onChange={setInputValue} onSend={handleSend} onStop={handleStop} onOpenSettings={() => setSettingsOpen(true)} onToggleThinking={handleToggleThinking} isStreaming={isStreaming || storyCompleted} disabled={isStreaming || storyCompleted} settings={settings} />
      </div>
    </div>
  );
}
