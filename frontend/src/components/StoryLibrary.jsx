import React, { useEffect, useState, useCallback, useRef } from 'react';
import { ArrowLeft, BookOpen, Plus, Clock, History, Globe, User, Play, Eye, EyeOff, StickyNote, Trash2, Search, X, Camera, ChevronRight, Flame } from 'lucide-react';
import { BASE_URL, authHeaders, parseJsonSafe, friendlyHttp, describeNetworkError } from '../utils/auth';
import { completePlaythrough } from '../utils/api';
import { fetchStoriesArt, fetchCast, fetchPrologue, uploadStoryArt, uploadCharacterArt, fileToDataUrl } from '../utils/art';

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const GRADIENTS = [
  'from-purple-700 via-fuchsia-700 to-rose-700',
  'from-blue-700 via-indigo-700 to-violet-700',
  'from-emerald-700 via-teal-700 to-cyan-700',
  'from-amber-600 via-orange-700 to-red-700',
  'from-slate-700 via-gray-700 to-zinc-800',
];
function genreGradient(genre) {
  let h = 0;
  const g = genre || '';
  for (let i = 0; i < g.length; i++) h = (h * 31 + g.charCodeAt(i)) >>> 0;
  return GRADIENTS[h % GRADIENTS.length];
}

function Cover({ src, title, genre, className, textClass }) {
  if (src) return <img src={src} alt={title || 'story cover'} className={`object-cover ${className}`} />;
  return (
    <div className={`bg-gradient-to-br ${genreGradient(genre)} flex items-center justify-center ${className}`}>
      <span className={`text-white/90 font-bold text-center px-2 drop-shadow-md ${textClass || 'text-sm'}`}>{title}</span>
    </div>
  );
}

export default function StoryLibrary({ user, onOpenStory, onNewStory, onBack }) {
  const [tab, setTab] = useState('all');
  const [allStories, setAllStories] = useState(null);
  const [myStories, setMyStories] = useState(null);
  const [history, setHistory] = useState(null);
  const [error, setError] = useState(null);
  const [selectedStory, setSelectedStory] = useState(null);

  // NEW UI state (feed)
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [chip, setChip] = useState('main');
  const [artMap, setArtMap] = useState({});

  // Detail state (all previous + new)
  const [detail, setDetail] = useState(null);
  const [notes, setNotes] = useState([]);
  const [noteText, setNoteText] = useState('');
  const [busyNote, setBusyNote] = useState(false);
  const [cast, setCast] = useState([]);
  const [prologue, setPrologue] = useState('');
  const [artTarget, setArtTarget] = useState(null);
  const [busyArt, setBusyArt] = useState(false);
  const [artError, setArtError] = useState(null);
  const [sessionMsg, setSessionMsg] = useState(null);
  const fileRef = useRef(null);

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

  // NEW: batch-load cover art once lists arrive
  useEffect(() => {
    const ids = Array.from(new Set([
      ...(allStories || []).map(s => s.id),
      ...(myStories || []).map(s => s.id),
      ...(history || []).map(h => h.story_id || h.id),
    ].filter(Boolean)));
    if (!ids.length) return;
    let alive = true;
    fetchStoriesArt(ids).then(m => { if (alive) setArtMap(prev => ({ ...prev, ...m })); });
    return () => { alive = false; };
  }, [allStories, myStories, history]);

  const loadDetails = useCallback(async (storyId) => {
    setDetail(null); setNotes([]); setCast([]); setPrologue(''); setArtError(null); setSessionMsg(null);
    const [dRes, nRes] = await Promise.allSettled([
      fetch(`${BASE_URL}/stories/${storyId}`, { headers: authHeaders() }),
      fetch(`${BASE_URL}/stories/${storyId}/notes`, { headers: authHeaders() }),
    ]);
    if (dRes.status === 'fulfilled') {
      const d = await parseJsonSafe(dRes.value);
      if (dRes.value.ok) setDetail(d);
    }
    if (nRes.status === 'fulfilled') {
      const n = await parseJsonSafe(nRes.value);
      if (nRes.value.ok && Array.isArray(n)) setNotes(n);
    }
    fetchCast(storyId).then(setCast);
    fetchPrologue(storyId).then(setPrologue);
  }, []);

  useEffect(() => { if (selectedStory) loadDetails(selectedStory.id); }, [selectedStory, loadDetails]);

  const isOwner = !!user && !!detail?.story?.creator_id && detail.story.creator_id === user.id;

  const addNote = async () => {
    const t = noteText.trim();
    if (!t || !selectedStory) return;
    setBusyNote(true);
    const res = await fetch(`${BASE_URL}/stories/${selectedStory.id}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ content: t, priority: 5 }),
    });
    if (res.ok) setNoteText('');
    await loadDetails(selectedStory.id);
    setBusyNote(false);
  };

  const toggleNote = async (n) => {
    await fetch(`${BASE_URL}/stories/${selectedStory.id}/notes/${n.id}/toggle`, { method: 'POST', headers: authHeaders() });
    loadDetails(selectedStory.id);
  };

  const deleteNote = async (n) => {
    await fetch(`${BASE_URL}/stories/${selectedStory.id}/notes/${n.id}`, { method: 'DELETE', headers: authHeaders() });
    loadDetails(selectedStory.id);
  };

  const toggleVisibility = async () => {
    const next = !(detail?.story?.is_public ?? true);
    await fetch(`${BASE_URL}/stories/${selectedStory.id}/visibility`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ is_public: next }),
    });
    loadDetails(selectedStory.id);
  };

  // NEW: art upload pipeline (owner only)
  const onArtFile = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file || !artTarget || !selectedStory) return;
    setBusyArt(true); setArtError(null);
    try {
      const dataUrl = await fileToDataUrl(file);
      if (artTarget.type === 'cover') {
        const res = await uploadStoryArt(selectedStory.id, 'cover', dataUrl);
        if (!res.ok) {
          const d = await parseJsonSafe(res);
          throw new Error(friendlyHttp(res.status, d?.detail));
        }
        setArtMap(prev => ({ ...prev, [selectedStory.id]: { ...(prev[selectedStory.id] || {}), cover_image: dataUrl } }));
        setDetail(d => (d ? { ...d, story: { ...d.story, cover_image: dataUrl } } : d));
      } else {
        const res = await uploadCharacterArt(selectedStory.id, artTarget.id, dataUrl);
        if (!res.ok) {
          const d = await parseJsonSafe(res);
          throw new Error(friendlyHttp(res.status, d?.detail));
        }
        setCast(cs => cs.map(c => (c.id === artTarget.id ? { ...c, image: dataUrl } : c)));
      }
      setSessionMsg('Image saved ✔');
    } catch (err) {
      setArtError(err.message || 'Upload failed');
    }
    setArtTarget(null);
    setBusyArt(false);
  };

  // NEW: session actions for sticky bar
  const resumePt = selectedStory
    ? (history || []).find(h => (h.story_id || h.id) === selectedStory.id && (h.status === 'active' || !h.status))
    : null;

  const doContinue = () => { onOpenStory(selectedStory); setSelectedStory(null); };

  const doNewSession = async () => {
    setSessionMsg(null);
    if (resumePt && resumePt.playthrough_id) {
      if (!window.confirm('Start a brand-new saga? Your current active run of this story will be completed first.')) return;
      const res = await completePlaythrough(resumePt.playthrough_id);
      if (!res.ok) { setSessionMsg('Could not close the old saga — try again.'); return; }
      load();
    }
    onOpenStory(selectedStory);
    setSelectedStory(null);
  };

  const tabs = [
    { id: 'all', label: 'All Sagas', icon: Globe },
    { id: 'mine', label: 'My Creations', icon: User },
    { id: 'history', label: 'History', icon: History },
  ];

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
      is_history: isHistory,
    });
  };

  // NEW: feed derivations
  const q = query.trim().toLowerCase();
  const matchQ = (s) => !q || (s.title || '').toLowerCase().includes(q) || (s.premise || '').toLowerCase().includes(q);
  const genres = Array.from(new Set((allStories || []).map(s => s.genre).filter(Boolean))).slice(0, 6);
  const ranked = [...(allStories || [])].sort((a, b) => (b.played_count || 0) - (a.played_count || 0));
  const weekAgo = Date.now() - 7 * 86400000;
  const applyChip = (list) => {
    if (chip === 'rankings') return [...list].sort((a, b) => (b.played_count || 0) - (a.played_count || 0));
    if (chip === 'today') return list.filter(s => new Date(s.updated_at).getTime() > weekAgo);
    if (chip !== 'main' && genres.includes(chip)) return list.filter(s => s.genre === chip);
    return list;
  };
  const scopeList = tab === 'all' ? allStories : tab === 'mine' ? myStories : history;
  const filtered = applyChip((scopeList || []).filter(matchQ));
  const featured = ranked.slice(0, 6);
  const recent = (history || []).slice(0, 10);
  const playedOf = (id) => {
    const s = (allStories || []).find(x => x.id === id);
    return s && s.played_count != null ? s.played_count : 0;
  };

  const renderCard = (s, isHistory) => (
    <button
      key={isHistory ? s.playthrough_id : s.id}
      onClick={() => handleCardClick(s, isHistory)}
      className="bg-gray-900/60 border border-gray-800 hover:border-purple-500/50 rounded-2xl p-3 text-left transition-all active:scale-95 touch-manipulation"
    >
      <Cover src={artMap[s.story_id || s.id]?.cover_image} title={s.title} genre={s.genre} className="w-full h-40 rounded-xl" />
      <div className="flex items-center justify-between mt-2">
        <span className="text-[10px] font-bold uppercase tracking-wide text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full">{s.genre}</span>
        <span className="text-[10px] text-gray-600 flex items-center gap-1"><Clock size={10} /> {timeAgo(s.updated_at)}</span>
      </div>
      <h3 className="text-base font-semibold text-white truncate mt-1.5">{s.title}</h3>
      <p className="text-xs text-gray-500 line-clamp-2 mt-1">{s.premise}</p>
      <p className="text-[11px] text-gray-400 mt-2 truncate">
        {s.character_name ? `${s.character_name} · ` : ''}
        {s.creator_name ? `by ${s.creator_name} · ` : ''}
        {isHistory ? `Day ${s.current_day} · ${s.time_of_day}` : `${s.played_count > 0 ? `${s.played_count} plays` : 'New'}`}
      </p>
    </button>
  );

  const renderRowCard = (s, isHistory, rank) => (
    <button
      key={(isHistory ? s.playthrough_id : s.id) + '-row'}
      onClick={() => handleCardClick(s, isHistory)}
      className="w-32 flex-shrink-0 text-left active:scale-95 touch-manipulation"
    >
      <div className="relative">
        <Cover src={artMap[s.story_id || s.id]?.cover_image} title={s.title} genre={s.genre} className="w-32 h-44 rounded-xl" textClass="text-xs" />
        {rank != null && (
          <span className="absolute top-1.5 left-1.5 w-6 h-6 rounded-lg bg-black/70 text-white text-xs font-bold flex items-center justify-center">{rank}</span>
        )}
      </div>
      <p className="text-xs text-gray-300 truncate mt-1.5">{s.title}</p>
      <p className="text-[10px] text-gray-600 truncate">{isHistory ? `Day ${s.current_day}` : `${s.played_count || 0} plays`}</p>
    </button>
  );

  /* ───────────────────────── STORY INFORMATION (detail) ───────────────────────── */
  if (selectedStory) {
    const protagonist = (cast.length ? cast : (detail?.characters || [])).find(c => c.is_player) || (cast[0] || null);
    const isPublic = detail?.story?.is_public ?? true;
    const coverSrc = detail?.story?.cover_image || artMap[selectedStory.id]?.cover_image || '';
    const storyMeta = detail?.story?.metadata || {};
    const storyDesc = storyMeta.rules || storyMeta.system_prompt || selectedStory.premise;
    const [infoTab, setInfoTab] = useState('info');

    return (
      <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col">
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onArtFile} />

        <header className="flex items-center gap-2 px-3 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
          <button onClick={() => setSelectedStory(null)} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-white truncate">Story Information</h2>
          </div>
          {isOwner && detail && (
            <button onClick={toggleVisibility} className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs min-h-[44px] touch-manipulation" title={isPublic ? 'Make private' : 'Make public'}>
              {isPublic ? <Eye size={14} /> : <EyeOff size={14} />}
              {isPublic ? 'Public' : 'Private'}
            </button>
          )}
        </header>

        <div className="flex border-b border-gray-800 bg-gray-900 flex-shrink-0">
          {[{ id: 'info', label: 'Information' }, { id: 'comments', label: "Director's Notes" }].map(t => (
            <button key={t.id} onClick={() => setInfoTab(t.id)} className={`flex-1 py-3 text-sm font-medium min-h-[44px] touch-manipulation border-b-2 ${infoTab === t.id ? 'text-white border-white' : 'text-gray-500 border-transparent'}`}>
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto pb-28">
          {infoTab === 'info' ? (
            <div>
              {/* Cover */}
              <div className="flex justify-center pt-8 pb-6 bg-gradient-to-b from-gray-900 to-gray-950">
                <div className="relative">
                  <Cover src={coverSrc} title={selectedStory.title} genre={selectedStory.genre} className="w-52 h-72 rounded-2xl border border-gray-700 shadow-2xl" textClass="text-lg" />
                  <span className="absolute top-2 right-2 text-[10px] font-bold uppercase tracking-wide text-lime-300 bg-black/70 px-2 py-0.5 rounded-full">{selectedStory.genre}</span>
                  {isOwner && (
                    <button onClick={() => { setArtTarget({ type: 'cover' }); fileRef.current?.click(); }} className="absolute bottom-2 right-2 p-2.5 rounded-xl bg-black/70 text-white min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation" title="Upload cover image">
                      <Camera size={16} />
                    </button>
                  )}
                </div>
              </div>

              <div className="px-5">
                <h1 className="text-2xl font-bold text-white">{selectedStory.title}</h1>
                {selectedStory.creator_name && <p className="text-xs text-gray-500 mt-1">@ {selectedStory.creator_name}</p>}

                {/* Tag chips */}
                <div className="flex flex-wrap gap-2 mt-3">
                  <span className="text-xs px-3 py-1.5 rounded-lg bg-gray-800 border border-gray-700 text-gray-300">{selectedStory.genre}</span>
                  <span className="text-xs px-3 py-1.5 rounded-lg bg-gray-800 border border-gray-700 text-gray-300">{isPublic ? 'Public' : 'Private'}</span>
                  <span className="text-xs px-3 py-1.5 rounded-lg bg-gray-800 border border-gray-700 text-gray-300">AI RPG</span>
                  {selectedStory.is_history && <span className="text-xs px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-300">In Progress</span>}
                </div>

                {/* Stats */}
                <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
                  <span className="flex items-center gap-1"><Play size={12} /> {playedOf(selectedStory.id)} plays</span>
                  <span className="flex items-center gap-1"><Clock size={12} /> {timeAgo(detail?.story?.updated_at || new Date().toISOString())}</span>
                </div>

                {/* Description */}
                <section className="mt-6">
                  <h3 className="text-base font-bold text-white mb-2">Description</h3>
                  <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-wrap">{selectedStory.premise}</p>
                </section>

                {/* Story Description */}
                <section className="mt-6 pt-5 border-t border-gray-800">
                  <h3 className="text-base font-bold text-white mb-2">Story Description</h3>
                  <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{storyDesc}</p>
                </section>

                {/* Setting / Cast with NPC portraits */}
                <section className="mt-6 pt-5 border-t border-gray-800">
                  <h3 className="text-base font-bold text-white mb-3">Setting · Characters</h3>
                  {cast.length === 0 && <p className="text-xs text-gray-600">Loading cast…</p>}
                  <div className="space-y-3">
                    {cast.map(c => (
                      <div key={c.id} className="flex items-center gap-3 bg-gray-900/60 border border-gray-800 rounded-xl p-3">
                        <div className="relative flex-shrink-0">
                          {c.image ? (
                            <img src={c.image} alt={c.name} className="w-14 h-14 rounded-xl object-cover" />
                          ) : (
                            <div className={`w-14 h-14 rounded-xl bg-gradient-to-br ${genreGradient(c.role)} flex items-center justify-center`}>
                              <span className="text-white font-bold">{(c.name || '?').charAt(0)}</span>
                            </div>
                          )}
                          {isOwner && (
                            <button onClick={() => { setArtTarget({ type: 'char', id: c.id }); fileRef.current?.click(); }} className="absolute -bottom-1.5 -right-1.5 p-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-300 min-w-[32px] min-h-[32px] flex items-center justify-center touch-manipulation" title={`Upload ${c.name} portrait`}>
                              <Camera size={12} />
                            </button>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-white truncate">
                            {c.name} {c.is_player && <span className="text-purple-400 text-[10px] font-bold uppercase ml-1">Protagonist</span>}
                          </p>
                          <p className="text-xs text-gray-500 truncate">{c.role}</p>
                          {c.background && <p className="text-xs text-gray-400 line-clamp-2 mt-1">{c.background}</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {/* Prologue Preview */}
                {prologue && (
                  <section className="mt-6 pt-5 border-t border-gray-800">
                    <h3 className="text-base font-bold text-white mb-3">Prologue Preview</h3>
                    <div className="border-l-4 border-gray-700 pl-4">
                      <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-wrap line-clamp-6">{prologue}</p>
                    </div>
                  </section>
                )}

                {artError && <p className="mt-4 text-xs text-red-400">{artError}</p>}
                {busyArt && <p className="mt-4 text-xs text-gray-500">Uploading image…</p>}
                {sessionMsg && <p className="mt-4 text-xs text-lime-400">{sessionMsg}</p>}
              </div>
            </div>
          ) : (
            /* ── Director's Notes tab (previous functionality preserved) ── */
            <div className="p-5">
              <div className="bg-gray-900/60 border border-gray-800 rounded-2xl p-5">
                <h3 className="text-xs font-bold uppercase tracking-wide text-amber-400 mb-3 flex items-center gap-1.5">
                  <StickyNote size={13} /> Director's Notes
                </h3>
                {notes.length === 0 && <p className="text-xs text-gray-600 mb-3">No directives yet. Notes here steer the AI narrator for every playthrough.</p>}
                <ul className="space-y-2 mb-4">
                  {notes.map(n => (
                    <li key={n.id} className={`flex items-start gap-2 px-3 py-2 rounded-xl border ${n.is_active ? 'border-amber-500/30 bg-amber-500/5' : 'border-gray-700 bg-gray-800/40 opacity-60'}`}>
                      <p className="flex-1 text-xs text-gray-300">{n.content}</p>
                      {isOwner && (
                        <>
                          <button onClick={() => toggleNote(n)} className="px-2 min-h-[44px] text-[10px] text-gray-400 hover:text-white touch-manipulation">
                            {n.is_active ? 'Pause' : 'Enable'}
                          </button>
                          <button onClick={() => deleteNote(n)} className="p-2.5 min-h-[44px] min-w-[44px] text-red-400 hover:text-red-300 touch-manipulation">
                            <Trash2 size={13} />
                          </button>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
                {isOwner && (
                  <div className="flex gap-2">
                    <input
                      value={noteText}
                      onChange={e => setNoteText(e.target.value)}
                      maxLength={500}
                      placeholder="e.g. Keep the tone grim; never let the dragon die."
                      className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-3 py-2.5 text-xs text-gray-200 min-h-[44px] focus:outline-none focus:border-amber-500/50"
                    />
                    <button onClick={addNote} disabled={busyNote || !noteText.trim()} className="px-4 min-h-[44px] rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium touch-manipulation active:scale-95 disabled:opacity-50">
                      {busyNote ? '…' : 'Add'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Sticky session bar (Continue / New Session) */}
        <div className="fixed bottom-0 inset-x-0 z-30 bg-gray-950/95 backdrop-blur border-t border-gray-800 px-4 py-3 flex gap-3">
          {resumePt && (
            <button onClick={doContinue} className="flex-1 bg-gray-800 hover:bg-gray-700 text-white font-bold py-4 rounded-xl text-sm active:scale-95 touch-manipulation min-h-[56px]">
              Continue Session
            </button>
          )}
          <button onClick={doNewSession} className="flex-1 bg-white hover:bg-gray-200 text-gray-900 font-bold py-4 rounded-xl text-sm active:scale-95 touch-manipulation min-h-[56px] flex items-center justify-center gap-2">
            <Play size={16} fill="currentColor" />
            {resumePt ? 'New Session' : (selectedStory.is_history ? 'Resume Journey' : 'New Session')}
          </button>
        </div>
      </div>
    );
  }

  /* ───────────────────────── FEED (home) ───────────────────────── */
  return (
    <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col">
      <header className="flex items-center gap-2 px-4 py-3 bg-gray-950 flex-shrink-0">
        <button onClick={onBack} className="p-2.5 -ml-2 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
          <ArrowLeft size={18} />
        </button>
        <h2 className="text-xl font-extrabold text-white">Story</h2>
        <span className="text-xl font-extrabold text-gray-600">Forge</span>
        <div className="flex-1" />
        <button onClick={() => { setSearchOpen(o => !o); setQuery(''); }} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-300 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
          <Search size={18} />
        </button>
        <button onClick={onNewStory} className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium min-h-[44px] touch-manipulation active:scale-95">
          <Plus size={16} /> New
        </button>
      </header>

      {searchOpen && (
        <div className="px-4 pb-2 flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 bg-gray-800 border border-gray-700 rounded-xl px-3">
            <Search size={14} className="text-gray-500" />
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search sagas…" className="flex-1 bg-transparent py-3 text-sm text-gray-200 focus:outline-none min-h-[44px]" />
            {query && <button onClick={() => setQuery('')} className="p-2 text-gray-500 touch-manipulation"><X size={14} /></button>}
          </div>
        </div>
      )}

      {/* Scope segmented control (previous tabs preserved) */}
      <div className="flex gap-2 px-4 py-2 overflow-x-auto flex-shrink-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap min-h-[40px] touch-manipulation ${tab === t.id ? 'bg-purple-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
            <t.icon size={14} /> {t.label}
          </button>
        ))}
      </div>

      {/* Category chips */}
      <div className="flex gap-2 px-4 py-2 overflow-x-auto flex-shrink-0 border-b border-gray-800 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {[{ id: 'main', label: 'Main' }, { id: 'rankings', label: 'Rankings' }, { id: 'today', label: 'Today' }, ...genres.map(g => ({ id: g, label: g }))].map(c => (
          <button key={c.id} onClick={() => setChip(c.id)} className={`px-4 py-2 rounded-xl text-xs font-medium whitespace-nowrap min-h-[40px] touch-manipulation border ${chip === c.id ? 'border-lime-400 text-lime-300' : 'border-gray-700 text-gray-400'}`}>
            {c.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto pb-8">
        {error && (
          <div className="max-w-4xl mx-auto mx-4 mt-4 px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        {scopeList === null && !error && <p className="text-center text-gray-500 text-sm mt-12">Loading…</p>}

        {scopeList !== null && scopeList.length === 0 && !error && (
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
            <button onClick={onNewStory} className="bg-gradient-to-r from-purple-600 to-blue-600 text-white font-bold px-6 py-3 rounded-lg touch-manipulation active:scale-95">
              Create a Saga
            </button>
          </div>
        )}

        {scopeList !== null && scopeList.length > 0 && (
          <div>
            {/* Featured banner row */}
            {tab === 'all' && !q && chip === 'main' && featured.length > 0 && (
              <div className="mt-4 flex gap-3 overflow-x-auto px-4 snap-x [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {featured.map((s, i) => (
                  <button key={s.id + '-feat'} onClick={() => handleCardClick(s, false)} className="relative w-64 h-72 flex-shrink-0 snap-center rounded-2xl overflow-hidden active:scale-95 touch-manipulation">
                    <Cover src={artMap[s.id]?.cover_image} title={s.title} genre={s.genre} className="w-full h-full" textClass="text-xl" />
                    <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent p-4 pt-10 text-left">
                      <h3 className="text-lg font-bold text-white leading-tight">{s.title}</h3>
                      <p className="text-xs text-gray-300 line-clamp-1 mt-1">{s.premise}</p>
                    </div>
                    {i === 0 && <span className="absolute top-2 left-2 flex items-center gap-1 text-[10px] font-bold text-orange-300 bg-black/70 px-2 py-1 rounded-full"><Flame size={10} /> FEATURED</span>}
                  </button>
                ))}
              </div>
            )}

            {/* Recently Played */}
            {recent.length > 0 && !q && (
              <section className="mt-6">
                <h3 className="text-base font-bold text-white px-4 mb-3">Recently Played Stories</h3>
                <div className="flex gap-3 overflow-x-auto px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                  {recent.map(s => renderRowCard(s, true))}
                </div>
              </section>
            )}

            {/* Top Ranked */}
            {tab === 'all' && ranked.length > 0 && !q && (
              <section className="mt-6">
                <div className="flex items-center justify-between px-4 mb-3">
                  <h3 className="text-base font-bold text-white">Top Ranked</h3>
                  <ChevronRight size={16} className="text-gray-600" />
                </div>
                <div className="flex gap-3 overflow-x-auto px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                  {ranked.slice(0, 8).map((s, i) => renderRowCard(s, false, i + 1))}
                </div>
              </section>
            )}

            {/* Grid */}
            <section className="mt-6 px-4">
              <h3 className="text-base font-bold text-white mb-3">{tab === 'mine' ? 'My Creations' : tab === 'history' ? 'History' : 'All Sagas'}</h3>
              {filtered.length === 0 ? (
                <p className="text-sm text-gray-600 text-center py-8">Nothing matches this filter.</p>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 max-w-4xl mx-auto">
                  {filtered.map(s => renderCard(s, tab === 'history'))}
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
