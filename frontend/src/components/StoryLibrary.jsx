import React, { useEffect, useState, useCallback, useRef } from 'react';
import { ArrowLeft, BookOpen, Plus, Clock, History, Globe, User, Image as ImageIcon, Heart, MessageCircle } from 'lucide-react';
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

export default function StoryLibrary({ user, onOpenStory, onNewStory, onBack }) {
  const [tab, setTab] = useState('all');
  const [allStories, setAllStories] = useState(null);
  const [myStories, setMyStories] = useState(null);
  const [history, setHistory] = useState(null);
  const [art, setArt] = useState({});
  const [social, setSocial] = useState({});
  const [error, setError] = useState(null);
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

  const uploadArt = async (file) => {
    const storyId = uploadTarget.current;
    if (!storyId || !file) return;
    try {
      if (!file.type.startsWith('image/')) { setError('Choose an image file.'); return; }
      const dataUrl = await fileToDataUrl(file);
      const res = await fetch(`${BASE_URL}/stories/${storyId}/art`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ image: dataUrl }),
      });
      const data = await parseJsonSafe(res);
      if (!res.ok) { setError(friendlyHttp(res.status, data?.detail)); return; }
      await load();
    } catch (e) {
      setError('Picture upload failed: ' + describeNetworkError(e));
    }
  };

  const tabs = [
    { id: 'all', label: 'All Sagas', icon: Globe },
    { id: 'mine', label: 'My Creations', icon: User },
    { id: 'history', label: 'History', icon: History },
  ];

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
              <button
                onClick={e => { e.stopPropagation(); uploadTarget.current = sid; fileRef.current?.click(); }}
                className="min-w-[44px] min-h-[32px] px-2 flex items-center justify-center gap-1 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-[10px] touch-manipulation active:scale-95"
                title="Set cover picture"
              >
                <ImageIcon size={12} /> Art
              </button>
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
              {soc.likes > 0 && <span className="flex items-center gap-0.5"><Heart size={10} className="text-pink-400" /> {soc.likes}</span>}
              {soc.comments > 0 && <span className="flex items-center gap-0.5"><MessageCircle size={10} className="text-blue-400" /> {soc.comments}</span>}
            </span>
          )}
        </p>
      </button>
    );
  };

  const list = tab === 'all' ? allStories : tab === 'mine' ? myStories : history;

  return (
    <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col">
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
