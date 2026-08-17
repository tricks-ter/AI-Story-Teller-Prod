import React, { useEffect, useState } from 'react';
import { ArrowLeft, Play, Plus, Pencil, Globe, Lock, Users, Sparkles, Image as ImageIcon, MapPin, Feather } from 'lucide-react';
import { BASE_URL, authHeaders, parseJsonSafe, describeNetworkError } from '../utils/auth';

export default function StoryDetails({ story, user, onBack, onStartJourney, onEdit }) {
  const [full, setFull] = useState(story || null);
  const [loading, setLoading] = useState(!story?.premise);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (story?.premise) return; // already have rich data
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`${BASE_URL}/stories/${story.id}`, { headers: authHeaders() });
        const data = await parseJsonSafe(res);
        if (!res.ok) throw new Error(data?.detail || 'Could not load story');
        if (alive) setFull({ ...story, ...data.story, characters: data.characters || [] });
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

  return (
    <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col">
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
        {isOwner && (
          <button
            onClick={() => onEdit(full || story)}
            className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium min-h-[44px] touch-manipulation active:scale-95"
          >
            <Pencil size={14} /> Edit
          </button>
        )}
      </header>

      {err && (
        <div className="px-4 py-3 bg-red-500/10 border-b border-red-500/20 text-red-400 text-sm">{err}</div>
      )}

      <div className="flex-1 overflow-y-auto">
        {banner && (
          <div className="h-40 sm:h-56 w-full overflow-hidden bg-gray-900 flex items-center justify-center">
            <img src={banner} alt={full?.title} className="w-full h-full object-cover" />
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
              {(meta.starter_location) && (
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
          </div>

          <div>
            <h3 className="text-[11px] uppercase tracking-wide text-gray-500 font-bold mb-1.5">Premise</h3>
            <p className="text-sm text-gray-300 leading-relaxed">{full?.premise || story.premise}</p>
          </div>

          {cast.length > 0 && (
            <div>
              <h3 className="text-[11px] uppercase tracking-wide text-gray-500 font-bold mb-2 flex items-center gap-1.5">
                <Users size={12} /> Cast
              </h3>
              <div className="space-y-2">
                {cast.map(c => (
                  <div key={c.id} className="bg-gray-900/60 border border-gray-800 rounded-xl p-3 flex items-start gap-3">
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
                      {c.background && <p className="text-[11px] text-gray-400 mt-0.5 line-clamp-2">{c.background}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!banner && (
            <div className="bg-gray-900/60 border border-dashed border-gray-700 rounded-xl p-5 flex items-center gap-3 text-gray-400 text-xs">
              <ImageIcon size={16} className="flex-shrink-0" />
              <p>No cover art yet{isOwner ? ' — tap Edit to add one.' : '.'}</p>
            </div>
          )}

          <div className="pt-2 flex flex-col gap-2">
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
