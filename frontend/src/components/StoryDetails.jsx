import React, { useEffect, useState } from 'react';
import { ArrowLeft, Play, Plus, Pencil, Globe, Lock, Users, Sparkles, Image as ImageIcon, Heart, MessageCircle, Send, Trash2, MapPin, Feather, Share2 } from 'lucide-react';
import { BASE_URL, authHeaders, parseJsonSafe, describeNetworkError } from '../utils/auth';
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

export default function StoryDetails({ story, user, onBack, onStartJourney, onEdit }) {
  const [full, setFull] = useState(story || null);
  const [social, setSocial] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [expandedCast, setExpandedCast] = useState({});
  const [commentText, setCommentText] = useState('');
  const [posting, setPosting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!story?.id) return;
    let alive = true;
    (async () => {
      try {
        const [sRes, socRes] = await Promise.all([
          fetch(`${BASE_URL}/stories/${story.id}`, { headers: authHeaders() }),
          fetch(`${BASE_URL}/stories/${story.id}/social`, { headers: authHeaders() }),
        ]);
        const data = await parseJsonSafe(sRes);
        if (!sRes.ok) throw new Error(data?.detail || 'Could not load story');
        const soc = socRes.ok ? await parseJsonSafe(socRes) : null;
        if (!alive) return;
        setFull(prev => ({ ...(prev || story), ...data.story, characters: data.characters || [] }));
        if (soc) setSocial(soc);
      } catch (e) {
        if (alive) setErr(describeNetworkError(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [story?.id]);

  if (!story) return null;

  const isOwner = (full?.creator_id === user?.id) || (!full?.creator_id) || full?.creator_id === 'legacy-system';
  const hasJourney = (full?.played_count || story.played_count || 0) > 0;
  const isPublic = full?.is_public ?? story.is_public ?? true;
  const cast = (full?.characters || []).slice(0, 6);
  const banner = full?.banner_image || full?.cover_image;
  const meta = full?.metadata || {};

  const handleCopyLink = async () => {
    const url = `${window.location.origin}${window.location.pathname}?story=${story.id}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.success('Share link copied');
    } catch {
      try {
        const ta = document.createElement('textarea');
        ta.value = url;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        toast.success('Share link copied');
      } catch {
        toast.error('Could not copy the link');
      }
    }
  };

  const handleLike = async () => {
    try {
      const res = await fetch(`${BASE_URL}/stories/${story.id}/like`, { method: 'POST', headers: authHeaders() });
      const data = await parseJsonSafe(res);
      if (res.ok) setSocial(prev => ({ ...(prev || { comments: [] }), ...data }));
    } catch (e) { console.warn('[like]', e); }
  };

  const handlePostComment = async () => {
    const content = commentText.trim();
    if (!content || posting) return;
    setPosting(true);
    try {
      const res = await fetch(`${BASE_URL}/stories/${story.id}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ content }),
      });
      const data = await parseJsonSafe(res);
      if (res.ok) {
        setSocial(prev => ({ ...(prev || { liked: false, like_count: 0 }), comments: [data, ...(prev?.comments || [])] }));
        setCommentText('');
        toast.success('Comment posted');
      } else {
        toast.error(data?.detail || 'Could not post comment');
      }
    } catch (e) {
      toast.error(describeNetworkError(e));
    } finally {
      setPosting(false);
    }
  };

  const handleDeleteComment = async (cid) => {
    try {
      const res = await fetch(`${BASE_URL}/stories/${story.id}/comments/${cid}`, { method: 'DELETE', headers: authHeaders() });
      if (res.ok) {
        setSocial(prev => prev ? { ...prev, comments: (prev.comments || []).filter(c => c.id !== cid) } : prev);
        toast.success('Comment deleted');
      }
    } catch (e) { console.warn('[delete comment]', e); }
  };

  const handleDeleteStory = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
      return;
    }
    try {
      const res = await fetch(`${BASE_URL}/stories/${story.id}`, { method: 'DELETE', headers: authHeaders() });
      if (res.ok) { toast.success('Saga deleted'); onBack(); }
      else {
        const data = await parseJsonSafe(res);
        toast.error(data?.detail || 'Could not delete the saga');
        setConfirmDelete(false);
      }
    } catch (e) {
      toast.error(describeNetworkError(e));
      setConfirmDelete(false);
    }
  };

  return (
    <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col">
      <Toaster />
      <header className="flex items-center gap-2 px-3 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
        <button onClick={onBack} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold text-white truncate">{full?.title || story.title}</h2>
          <p className="text-xs text-gray-500 truncate">
            {full?.creator_name ? `by ${full.creator_name}` : (story.creator_name ? `by ${story.creator_name}` : 'Unknown author')}
          </p>
        </div>
        <button
          onClick={handleCopyLink}
          className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium min-h-[44px] touch-manipulation active:scale-95"
          title="Copy share link"
        >
          <Share2 size={14} /> Share
        </button>
        {isOwner && (
          <>
            <button
              onClick={() => onEdit(full || story)}
              className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium min-h-[44px] touch-manipulation active:scale-95"
            >
              <Pencil size={14} /> Edit
            </button>
            <button
              onClick={handleDeleteStory}
              className={`flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-medium min-h-[44px] touch-manipulation active:scale-95 ${confirmDelete ? 'bg-red-600 text-white' : 'bg-gray-800 hover:bg-red-600/40 text-red-400'}`}
              title="Delete saga"
            >
              {confirmDelete ? 'Sure?' : <Trash2 size={14} />}
            </button>
          </>
        )}
      </header>

      {err && (
        <div className="px-4 py-3 bg-red-500/10 border-b border-red-500/20 text-red-400 text-sm flex items-center justify-between">
          <span>{err}</span>
          <button onClick={() => setErr(null)} className="text-red-300 text-xs underline">dismiss</button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {banner && (
          <div className="h-40 sm:h-56 w-full overflow-hidden bg-gray-900">
            <img src={banner} alt={full?.title || story.title} className="w-full h-full object-cover" />
          </div>
        )}

        <div className="px-4 sm:px-6 py-5 max-w-3xl mx-auto space-y-5">
          <div>
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span className="text-[10px] font-bold uppercase tracking-wide text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full">{full?.genre || story.genre}</span>
              {isPublic ? (
                <span className="text-[10px] text-emerald-400 flex items-center gap-1"><Globe size={10} /> Public</span>
              ) : (
                <span className="text-[10px] text-amber-400 flex items-center gap-1"><Lock size={10} /> Private</span>
              )}
              {meta.starter_location && (
                <span className="text-[10px] text-blue-300 flex items-center gap-1"><MapPin size={10} /> {meta.starter_location}</span>
              )}
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-white leading-tight">{full?.title || story.title}</h1>
            {(full?.creator_name || story.creator_name) && (
              <p className="text-sm text-gray-400 mt-1">
                by <span className="text-gray-200 font-medium">{full?.creator_name || story.creator_name}</span>
              </p>
            )}
            {meta.tone && (
              <p className="text-xs text-gray-500 italic mt-2 flex items-center gap-1.5"><Feather size={11} /> {meta.tone}</p>
            )}
            {/* Like button */}
            <div className="flex items-center gap-3 mt-3">
              <button
                onClick={handleLike}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium min-h-[44px] touch-manipulation active:scale-95 transition-colors ${
                  social?.liked ? 'bg-pink-500/20 text-pink-400 border border-pink-500/40' : 'bg-gray-800 text-gray-300 border border-gray-700 hover:bg-gray-700'
                }`}
              >
                <Heart size={16} className={social?.liked ? 'fill-pink-400' : ''} />
                {social?.liked ? 'Liked' : 'Like'}
                <span className="text-xs opacity-80">({social?.like_count ?? 0})</span>
              </button>
              <span className="flex items-center gap-1.5 text-xs text-gray-500">
                <MessageCircle size={13} /> {(social?.comments || []).length} comment{(social?.comments || []).length === 1 ? '' : 's'}
              </span>
            </div>
          </div>

          <div>
            <h3 className="text-[11px] uppercase tracking-wide text-gray-500 font-bold mb-1.5">Premise</h3>
            <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{full?.premise || story.premise}</p>
          </div>

          {cast.length > 0 && (
            <div>
              <h3 className="text-[11px] uppercase tracking-wide text-gray-500 font-bold mb-2 flex items-center gap-1.5">
                <Users size={12} /> Cast <span className="normal-case font-normal text-gray-600">— tap a card for full background</span>
              </h3>
              <div className="space-y-2">
                {cast.map(c => {
                  const expanded = !!expandedCast[c.id];
                  return (
                    <div
                      key={c.id}
                      onClick={() => setExpandedCast(p => ({ ...p, [c.id]: !p[c.id] }))}
                      className="bg-gray-900/60 border border-gray-800 hover:border-purple-500/40 rounded-xl p-3 flex items-start gap-3 cursor-pointer touch-manipulation active:scale-[0.99] transition-colors"
                    >
                      {c.image ? (
                        <img src={c.image} alt={c.name} className="w-10 h-10 rounded-lg object-cover flex-shrink-0 bg-gray-800" />
                      ) : (
                        <div className="w-10 h-10 rounded-lg bg-gray-800 flex items-center justify-center flex-shrink-0">
                          <Sparkles size={14} className="text-purple-400" />
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-white truncate">{c.name}</p>
                          {c.is_player && <span className="text-[9px] uppercase font-bold text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">You</span>}
                        </div>
                        <p className="text-[11px] text-gray-500">{c.role}</p>
                        {c.background && (
                          <p className={`text-[11px] text-gray-400 mt-0.5 ${expanded ? 'whitespace-pre-wrap' : 'line-clamp-2'}`}>{c.background}</p>
                        )}
                        {c.background && !expanded && <p className="text-[10px] text-purple-400/70 mt-1">Read more ▾</p>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Comments */}
          <div>
            <h3 className="text-[11px] uppercase tracking-wide text-gray-500 font-bold mb-2 flex items-center gap-1.5">
              <MessageCircle size={12} /> Reader Comments
            </h3>
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={commentText}
                onChange={e => setCommentText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handlePostComment(); }}
                placeholder="Share your thoughts…"
                maxLength={500}
                className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm text-white focus:border-purple-500 outline-none min-h-[44px]"
              />
              <button
                onClick={handlePostComment}
                disabled={!commentText.trim() || posting}
                className="px-4 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:opacity-40 text-white min-h-[44px] min-w-[44px] flex items-center justify-center touch-manipulation active:scale-95"
              >
                <Send size={15} />
              </button>
            </div>
            {(social?.comments || []).length === 0 ? (
              <p className="text-xs text-gray-600">No comments yet — be the first to react.</p>
            ) : (
              <div className="space-y-2">
                {(social?.comments || []).map(c => (
                  <div key={c.id} className="bg-gray-900/60 border border-gray-800 rounded-xl px-3 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-semibold text-purple-300 truncate">{c.username}</p>
                      <span className="flex items-center gap-2 flex-shrink-0">
                        <span className="text-[10px] text-gray-600">{timeAgo(c.created_at)}</span>
                        {(c.user_id === user?.id || isOwner) && (
                          <button onClick={() => handleDeleteComment(c.id)} className="text-gray-600 hover:text-red-400 min-w-[28px] min-h-[28px] flex items-center justify-center touch-manipulation" title="Delete comment">
                            <Trash2 size={12} />
                          </button>
                        )}
                      </span>
                    </div>
                    <p className="text-sm text-gray-300 mt-1 leading-relaxed whitespace-pre-wrap">{c.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {!banner && (
            <div className="bg-gray-900/60 border border-dashed border-gray-700 rounded-xl p-5 flex items-center gap-3 text-gray-400 text-xs">
              <ImageIcon size={16} className="flex-shrink-0" />
              <p>No cover art yet{isOwner ? ' — tap Edit to add one.' : '.'}</p>
            </div>
          )}

          <div className="pt-2 flex flex-col gap-2 pb-6">
            <button
              onClick={() => onStartJourney(full || story)}
              disabled={loading}
              className="flex items-center justify-center gap-2 px-4 py-3.5 rounded-xl bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white font-semibold text-sm min-h-[52px] touch-manipulation active:scale-95 disabled:opacity-50"
            >
              {hasJourney ? <><Play size={16} /> Continue Journey</> : <><Plus size={16} /> Begin New Journey</>}
            </button>
            <button
              onClick={onBack}
              className="px-4 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-medium min-h-[44px] touch-manipulation active:scale-95"
            >
              Back to Library
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
