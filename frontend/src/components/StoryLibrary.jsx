import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { ArrowLeft, BookOpen, Plus, Clock, History, Globe, User, Image as ImageIcon, Search, X as XIcon, Flame, Sparkles } from 'lucide-react';
import { BASE_URL, authHeaders, parseJsonSafe, friendlyHttp, describeNetworkError } from '../utils/auth';
import { toast } from '../utils/toast';
import Toaster from './Toaster';

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function fileToDataUrl(file, maxW = 640) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, maxW / img.width);
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL('image/jpeg', 0.82));
      };
      img.onerror = () => reject(new Error('bad image'));
      img.src = reader.result;
    };
    reader.onerror = () => reject(new Error('read failed'));
    reader.readAsDataURL(file);
  });
}

function SkeletonCard() {
  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-2xl p-4 animate-pulse">
      <div className="h-16 rounded-xl bg-gray-800 mb-3" />
      <div className="h-3 w-16 rounded bg-gray-800 mb-2" />
      <div className="h-5 w-3/4 rounded bg-gray-800 mb-2" />
      <div className="h-3 w-full rounded bg-gray-800" />
    </div>
  );
}

const ONBOARD_KEY = 'inkmind_onboarded';

export default function StoryLibrary({ user, onOpenStory, onNewStory, onBack }) {
  const [tab, setTab] = useState('all');
  const [allStories, setAllStories] = useState(null);
  const [myStories, setMyStories] = useState(null);
  const [history, setHistory] = useState(null);
  const [art, setArt] = useState({});
  const [social, setSocial] = useState({});
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [genreFilter, setGenreFilter] = useState('All');
  const [sortBy, setSortBy] = useState('recent');
  const [onboardDismissed, setOnboardDismissed] = useState(() => {
    try { return localStorage.getItem(ONBOARD_KEY) === '1'; } catch { return true; }
  });
  const fileRef = useRef(null);
  const uploadTarget = useRef(null);

  const load = useCallback(async () => {
    setError(null);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);

    const jobs = [
      fetch(`${BASE_URL}/stories?scope=all`, { headers: authHeaders(), signal: controller.signal }),
      fetch(`${BASE_URL}/stories?scope=mine`, { headers: authHeaders(), signal: controller.signal }),
      fetch(`${BASE_URL}/playthroughs`, { headers: authHeaders(), signal: controller.signal }),
      fetch(`${BASE_URL}/stories/art`, { headers: authHeaders(), signal: controller.signal }),
      fetch(`${BASE_URL}/stories/social`, { headers: authHeaders(), signal: controller.signal }),
    ];

    const results = await Promise.allSettled(jobs);
    clearTimeout(timer);

    const errs = [];
    const setters = [setAllStories, setMyStories, setHistory];
    const names = ['All Sagas', 'My Creations', 'History'];

    for (let i = 0; i < 3; i++) {
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

    const artRes = results[3];
    if (artRes.status === 'fulfilled' && artRes.value.ok) {
      try {
        const artData = await parseJsonSafe(artRes.value);
        const flat = {};
        if (artData && typeof artData === 'object') {
          for (const [k, v] of Object.entries(artData)) {
            if (v && typeof v === 'object') flat[k] = v.cover || '';
            else if (typeof v === 'string') flat[k] = v;
          }
        }
        setArt(flat);
      } catch { /* non-fatal */ }
    }

    const socRes = results[4];
    if (socRes.status === 'fulfilled' && socRes.value.ok) {
      try {
        const socData = await parseJsonSafe(socRes.value);
        if (socData && typeof socData === 'object') setSocial(socData);
      } catch { /* non-fatal */ }
    }

    if (errs.length) setError(errs.join('  •  '));
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setGenreFilter('All'); }, [tab]);

  const uploadArt = async (file) => {
    const storyId = uploadTarget.current;
    if (!storyId || !file) return;
    try {
      if (!file.type.startsWith('image/')) { toast.error('Choose an image file.'); return; }
      const dataUrl = await fileToDataUrl(file);
      const res = await fetch(`${BASE_URL}/stories/${storyId}/art`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ image: dataUrl }),
      });
      const data = await parseJsonSafe(res);
      if (!res.ok) { toast.error(friendlyHttp(res.status, data?.detail)); return; }
      toast.success('Cover updated');
      await load();
    } catch (e) {
      toast.error('Picture upload failed: ' + describeNetworkError(e));
    }
  };

  const tabs = [
    { id: 'all', label: 'All Sagas', icon: Globe },
    { id: 'mine', label: 'My Creations', icon: User },
    { id: 'history', label: 'History', icon: History },
  ];

  const currentList = tab === 'all' ? allStories : tab === 'mine' ? myStories : history;

  const genres = useMemo(() => {
    const src = tab === 'mine' ? myStories : allStories;
    return [...new Set((src || []).map(s => s.genre).filter(Boolean))];
  }, [tab, allStories, myStories]);

  const visible = useMemo(() => {
    let list = currentList || [];
    if (tab !== 'history') {
      if (genreFilter !== 'All') list = list.filter(s => s.genre === genreFilter);
      if (query.trim()) {
        const q = query.trim().toLowerCase();
        list = list.filter(s =>
          (s.title || '').toLowerCase().includes(q) ||
          (s.premise || '').toLowerCase().includes(q));
      }
      if (sortBy === 'played') list = [...list].sort((a, b) => (b.played_count || 0) - (a.played_count || 0));
      else if (sortBy === 'az') list = [...list].sort((a, b) => (a.title || '').localeCompare(b.title || ''));
    }
    return list;
  }, [currentList, tab, genreFilter, query, sortBy]);

  const dismissOnboard = () => {
    setOnboardDismissed(true);
    try { localStorage.setItem(ONBOARD_KEY, '1'); } catch {}
  };

  const renderCard = (s, isHistory) => {
    const sid = s.story_id || s.id;
    const cover = art[sid];
    const soc = social[sid];
    const authorName = s.creator_name || (isHistory ? null : (user?.username || null));
    const payload = {
      id: sid,
      story_id: s.story_id,
      title: s.title,
      genre: s.genre,
      premise: s.premise,
      character_name: s.character_name,
      character_role: s.character_role,
      creator_id: s.creator_id,
      creator_name: s.creator_name,
      is_public: s.is_public,
      played_count: s.played_count || 0,
      current_day: s.current_day,
      time_of_day: s.time_of_day,
      playthrough_id: isHistory ? s.playthrough_id : undefined,
    };
    return (
      <button
        key={isHistory ? s.playthrough_id : s.id}
        onClick={() => onOpenStory(payload)}
        className="bg-gray-900/60 border border-gray-800 hover:border-purple-500/50 rounded-2xl p-4 text-left transition-all active:scale-95 touch-manipulation"
      >
        {cover ? (
          <div className="h-32 rounded-xl overflow-hidden mb-3 bg-gray-800 relative">
            <img src={cover} alt={s.title} className="w-full h-full object-cover" />
          </div>
        ) : (
          <div className="h-16 rounded-xl mb-3 bg-gradient-to-br from-purple-900/40 to-blue-900/30 flex items-center justify-center">
            <BookOpen className="text-purple-500/50" size={22} />
          </div>
        )}
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] font-bold uppercase tracking-wide text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full">{s.genre}</span>
          <span className="flex items-center gap-2">
            {!isHistory && authorName === user?.username && (
              <span
                role="button"
                onClick={e => { e.stopPropagation(); uploadTarget.current = sid; fileRef.current?.click(); }}
                className="min-w-[44px] min-h-[32px] px-2 inline-flex items-center justify-center gap-1 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-[10px] touch-manipulation active:scale-95"
                title="Set cover picture"
              >
                <ImageIcon size={12} /> Art
              </span>
            )}
            <span className="text-[10px] text-gray-600 flex items-center gap-1"><Clock size={10} /> {timeAgo(s.updated_at)}</span>
          </span>
        </div>
        <h3 className="text-lg font-semibold text-white truncate">{s.title}</h3>
        <p className="text-sm text-gray-500 line-clamp-2 mt-1">{s.premise}</p>
        <p className="text-xs text-gray-400 mt-3 truncate flex items-center gap-1.5 flex-wrap">
          {s.character_name ? <span>{s.character_name} ·</span> : null}
          {authorName ? <span>by {authorName} ·</span> : null}
          {isHistory ? <span>Day {s.current_day} · {s.time_of_day}</span> : <span>{s.played_count > 0 ? 'Played' : 'New'}</span>}
          {!isHistory && soc && (soc.likes > 0 || soc.comments > 0) && (
            <span className="flex items-center gap-1.5 text-gray-500">
              {soc.likes > 0 && <span className="flex items-center gap-0.5"><span className="text-pink-400">♥</span> {soc.likes}</span>}
              {soc.comments > 0 && <span className="flex items-center gap-0.5"><span className="text-blue-400">💬</span> {soc.comments}</span>}
            </span>
          )}
        </p>
      </button>
    );
  };

  return (
    <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col">
      <Toaster />
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) uploadArt(f); }}
      />
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

        {/* Onboarding nudge */}
        {tab !== 'history' && myStories !== null && myStories.length === 0 && !onboardDismissed && (
          <div className="max-w-4xl mx-auto mb-4 flex items-center gap-3 bg-purple-500/10 border border-purple-500/20 rounded-xl px-4 py-3">
            <Sparkles size={16} className="text-purple-400 flex-shrink-0" />
            <p className="flex-1 text-xs text-purple-200 leading-snug">New here? Forge your first saga — pick a genre, set the premise, create your hero.</p>
            <button onClick={onNewStory} className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold min-h-[36px] touch-manipulation active:scale-95">Start</button>
            <button onClick={dismissOnboard} className="p-2 text-purple-300/70 hover:text-white min-w-[36px] min-h-[36px] flex items-center justify-center touch-manipulation"><XIcon size={14} /></button>
          </div>
        )}

        {/* Search + sort toolbar */}
        {tab !== 'history' && (
          <div className="max-w-4xl mx-auto mb-3 space-y-2">
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
                <input
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  placeholder="Search title or premise…"
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl pl-9 pr-9 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-purple-500 min-h-[44px]"
                />
                {query && (
                  <button onClick={() => setQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white p-1.5 touch-manipulation" title="Clear search">
                    <XIcon size={14} />
                  </button>
                )}
              </div>
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value)}
                className="bg-gray-900 border border-gray-800 rounded-xl px-3 text-xs text-gray-300 outline-none min-h-[44px] touch-manipulation"
                title="Sort"
              >
                <option value="recent">Newest</option>
                <option value="played">Most Played</option>
                <option value="az">A–Z</option>
              </select>
            </div>
            {genres.length > 1 && (
              <div className="flex gap-2 overflow-x-auto pb-1">
                {['All', ...genres].map(g => (
                  <button
                    key={g}
                    onClick={() => setGenreFilter(g)}
                    className={`px-3 py-1.5 rounded-full text-[11px] font-medium whitespace-nowrap min-h-[32px] touch-manipulation ${
                      genreFilter === g ? 'bg-purple-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
                    }`}
                  >
                    {g}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Recently Played shelf (All tab only) */}
        {tab === 'all' && history && history.length > 0 && (
          <div className="max-w-4xl mx-auto mb-4">
            <h3 className="text-[11px] uppercase tracking-wide text-gray-500 font-bold mb-2 flex items-center gap-1.5">
              <Flame size={12} className="text-amber-400" /> Recently Played
            </h3>
            <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
              {history.slice(0, 8).map(h => (
                <button
                  key={`shelf-${h.playthrough_id}`}
                  onClick={() => onOpenStory({
                    id: h.story_id,
                    story_id: h.story_id,
                    title: h.title,
                    genre: h.genre,
                    premise: h.premise,
                    character_name: h.character_name,
                    current_day: h.current_day,
                    time_of_day: h.time_of_day,
                    playthrough_id: h.playthrough_id,
                    played_count: 1,
                  })}
                  className="flex-shrink-0 w-40 bg-gray-900/60 border border-gray-800 hover:border-amber-500/40 rounded-xl p-3 text-left touch-manipulation active:scale-95"
                >
                  <div className="h-12 rounded-lg bg-gradient-to-br from-purple-900/40 to-blue-900/30 flex items-center justify-center mb-2">
                    <BookOpen className="text-purple-500/50" size={16} />
                  </div>
                  <p className="text-xs font-semibold text-white truncate">{h.title}</p>
                  <p className="text-[10px] text-gray-500 mt-0.5">Day {h.current_day} · {timeAgo(h.updated_at)}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Skeleton loaders */}
        {currentList === null && !error && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-4xl mx-auto">
            {[0, 1, 2, 3, 4, 5].map(i => <SkeletonCard key={i} />)}
          </div>
        )}

        {/* Empty states */}
        {currentList !== null && currentList.length === 0 && !error && (
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

        {/* No matches after filtering */}
        {currentList !== null && currentList.length > 0 && visible.length === 0 && !error && (
          <div className="text-center mt-12 px-6">
            <p className="text-sm text-gray-400 mb-4">No sagas match your search.</p>
            <button
              onClick={() => { setQuery(''); setGenreFilter('All'); }}
              className="px-4 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium min-h-[44px] touch-manipulation"
            >
              Clear filters
            </button>
          </div>
        )}

        {visible.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-4xl mx-auto">
            {visible.map(s => renderCard(s, tab === 'history'))}
          </div>
        )}
      </div>
    </div>
  );
}
