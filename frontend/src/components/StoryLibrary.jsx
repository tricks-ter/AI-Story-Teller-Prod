import React, { useEffect, useState, useCallback } from 'react';
import { ArrowLeft, BookOpen, Plus, Clock, History, Globe, User, Play } from 'lucide-react';
import { BASE_URL, authHeaders, parseJsonSafe, friendlyHttp, describeNetworkError } from '../utils/auth';

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function StoryLibrary({ user, onOpenStory, onNewStory, onBack }) {
  const [tab, setTab] = useState('all');
  const [allStories, setAllStories] = useState(null);
  const [myStories, setMyStories] = useState(null);
  const [history, setHistory] = useState(null);
  const [error, setError] = useState(null);
  
  // ADDITIVE: State to track the selected story for the Details View
  const [selectedStory, setSelectedStory] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);

    const jobs = [
      fetch(`${BASE_URL}/stories?scope=all`, { headers: authHeaders(), signal: controller.signal }),
      fetch(`${BASE_URL}/stories?scope=mine`, { headers: authHeaders(), signal: controller.signal }),
      fetch(`${BASE_URL}/playthroughs`, { headers: authHeaders(), signal: controller.signal }),
    ];

    const results = await Promise.allSettled(jobs);
    clearTimeout(timer);

    const errs = [];
    const setters = [setAllStories, setMyStories, setHistory];
    const names = ['All Sagas', 'My Creations', 'History'];

    for (let i = 0; i < results.length; i++) {
      const r = results[i];
      if (r.status === 'fulfilled') {
        try {
          const res = r.value;
          const data = await parseJsonSafe(res);
          if (res.ok) {
            setters[i](Array.isArray(data) ? data : []);
          } else {
            setters[i]([]);
            errs.push(`${names[i]}: ${friendlyHttp(res.status, data?.detail)}`);
          }
        } catch (e) {
          setters[i]([]);
          errs.push(`${names[i]}: parse error`);
        }
      } else {
        setters[i]([]);
        errs.push(`${names[i]}: ${describeNetworkError(r.reason)}`);
      }
    }

    if (errs.length) setError(errs.join('  •  '));
  }, []);

  useEffect(() => { load(); }, [load]);

  const tabs = [
    { id: 'all', label: 'All Sagas', icon: Globe },
    { id: 'mine', label: 'My Creations', icon: User },
    { id: 'history', label: 'History', icon: History },
  ];

  // ADDITIVE: Intercept click to show details instead of immediately playing
  const handleCardClick = (s, isHistory) => {
    setSelectedStory({
      id: s.story_id || s.id,
      title: s.title,
      genre: s.genre,
      premise: s.premise,
      character_name: s.character_name,
      character_role: s.character_role,
      creator_name: s.creator_name,
      current_day: s.current_day,
      time_of_day: s.time_of_day,
      is_history: isHistory
    });
  };

  const renderCard = (s, isHistory) => (
    <button
      key={isHistory ? s.playthrough_id : s.id}
      onClick={() => handleCardClick(s, isHistory)}
      className="bg-gray-900/60 border border-gray-800 hover:border-purple-500/50 rounded-2xl p-5 text-left transition-all active:scale-95 touch-manipulation"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-bold uppercase tracking-wide text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full">{s.genre}</span>
        <span className="text-[10px] text-gray-600 flex items-center gap-1"><Clock size={10} /> {timeAgo(s.updated_at)}</span>
      </div>
      <h3 className="text-lg font-semibold text-white truncate">{s.title}</h3>
      <p className="text-sm text-gray-500 line-clamp-2 mt-1">{s.premise}</p>
      <p className="text-xs text-gray-400 mt-3 truncate">
        {s.character_name ? `${s.character_name} · ` : ""}
        {s.creator_name ? `by ${s.creator_name} · ` : ""}
        {isHistory ? `Day ${s.current_day} · ${s.time_of_day}` : (s.played_count > 0 ? 'Played' : 'New')}
      </p>
    </button>
  );

  const list = tab === 'all' ? allStories : tab === 'mine' ? myStories : history;

  // ═══════════════════════════════════════════════════════════════
  // ADDITIVE: Story Details View (Forge Page)
  // ═══════════════════════════════════════════════════════════════
  if (selectedStory) {
    return (
      <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col">
        <header className="flex items-center gap-2 px-3 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
          <button onClick={() => setSelectedStory(null)} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-white truncate">Story Details</h2>
          </div>
        </header>
        
        <div className="flex-1 overflow-y-auto p-6 max-w-2xl mx-auto w-full">
          <div className="bg-gray-900/60 border border-gray-800 rounded-2xl p-6 mb-6 shadow-xl">
             <div className="flex items-center gap-2 mb-3">
               <span className="text-[10px] font-bold uppercase tracking-wide text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full">{selectedStory.genre}</span>
               {selectedStory.is_history && (
                 <span className="text-[10px] font-bold uppercase tracking-wide text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full">In Progress</span>
               )}
             </div>
             
             <h1 className="text-2xl sm:text-3xl font-bold text-white mb-4 leading-tight">{selectedStory.title}</h1>
             
             {selectedStory.is_history && (
               <p className="text-sm text-blue-400 mb-4 flex items-center gap-1.5">
                 <Clock size={14} /> Resuming from Day {selectedStory.current_day} · {selectedStory.time_of_day}
               </p>
             )}
             
             <div className="mb-6">
               <h3 className="text-xs font-bold uppercase tracking-wide text-gray-500 mb-2">The Premise</h3>
               <p className="text-gray-300 leading-relaxed whitespace-pre-wrap">{selectedStory.premise}</p>
             </div>
             
             <div className="border-t border-gray-800 pt-4">
                <h3 className="text-xs font-bold uppercase tracking-wide text-gray-500 mb-2">Protagonist</h3>
                <p className="text-lg font-bold text-white">
                  {selectedStory.character_name || "Unknown Hero"} 
                  <span className="text-gray-500 font-normal text-sm ml-2">({selectedStory.character_role || "Adventurer"})</span>
                </p>
             </div>

             {selectedStory.creator_name && (
               <p className="text-xs text-gray-500 mt-6 pt-4 border-t border-gray-800">Authored by {selectedStory.creator_name}</p>
             )}
          </div>

          <button
            onClick={() => { onOpenStory(selectedStory); setSelectedStory(null); }}
            className="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white font-bold py-4 rounded-xl text-lg shadow-lg shadow-purple-900/20 active:scale-95 touch-manipulation min-h-[56px] flex items-center justify-center gap-2 transition-all"
          >
            <Play size={20} fill="currentColor" />
            {selectedStory.is_history ? "Resume Journey" : "Start Journey"}
          </button>
        </div>
      </div>
    );
  }
  // ═══════════════════════════════════════════════════════════════

  return (
    <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col">
      <header className="flex items-center gap-2 px-3 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
        <button onClick={onBack} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold text-white truncate">Story Forge</h2>
          <p className="text-xs text-gray-500 truncate">{user?.username}</p>
        </div>
        <button
          onClick={onNewStory}
          className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium min-h-[44px] touch-manipulation active:scale-95"
        >
          <Plus size={16} /> New
        </button>
      </header>

      <div className="flex gap-2 px-3 py-2 border-b border-gray-800 bg-gray-900 overflow-x-auto flex-shrink-0">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap min-h-[40px] touch-manipulation ${
              tab === t.id ? 'bg-purple-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            <t.icon size={14} /> {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {error && (
          <div className="max-w-4xl mx-auto mb-4 px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        {list === null && !error && (
          <p className="text-center text-gray-500 text-sm mt-12">Loading…</p>
        )}

        {list !== null && list.length === 0 && !error && (
          <div className="text-center mt-16 px-6">
            <div className="bg-purple-500/10 text-purple-400 p-4 rounded-2xl w-fit mx-auto mb-4">
              <BookOpen className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">
              {tab === 'all' ? 'No sagas yet' : tab === 'mine' ? 'You have no creations' : 'No play history'}
            </h3>
            <p className="text-sm text-gray-500 mb-6">
              {tab === 'history' ? 'Play any saga and it will appear here.' : 'Forge your first story and begin an adventure.'}
            </p>
            <button
              onClick={onNewStory}
              className="bg-gradient-to-r from-purple-600 to-blue-600 text-white font-bold px-6 py-3 rounded-lg touch-manipulation active:scale-95"
            >
              Create a Saga
            </button>
          </div>
        )}

        {list !== null && list.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-4xl mx-auto">
            {list.map(s => renderCard(s, tab === 'history'))}
          </div>
        )}
      </div>
    </div>
  );
}
