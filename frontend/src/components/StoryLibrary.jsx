import React, { useEffect, useState } from 'react';
import { ArrowLeft, BookOpen, Plus, Clock } from 'lucide-react';
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
  const [stories, setStories] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    (async () => {
      try {
        const res = await fetch(`${BASE_URL}/stories`, { headers: authHeaders(), signal: controller.signal });
        const data = await parseJsonSafe(res);
        if (!res.ok) throw new Error(friendlyHttp(res.status, data?.detail));
        setStories(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error('[library] error:', err);
        setError(describeNetworkError(err));
        setStories([]);
      } finally {
        clearTimeout(timer);
      }
    })();
    return () => { clearTimeout(timer); controller.abort(); };
  }, []);

  return (
    <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col">
      <header className="flex items-center gap-2 px-3 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
        <button onClick={onBack} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold text-white truncate">Your Sagas</h2>
          <p className="text-xs text-gray-500 truncate">{user?.username}</p>
        </div>
        <button
          onClick={onNewStory}
          className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium min-h-[44px] touch-manipulation active:scale-95"
        >
          <Plus size={16} /> New Story
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-4">
        {error && (
          <div className="max-w-4xl mx-auto mb-4 px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        {stories === null && !error && (
          <p className="text-center text-gray-500 text-sm mt-12">Loading your sagas…</p>
        )}

        {stories !== null && stories.length === 0 && !error && (
          <div className="text-center mt-16 px-6">
            <div className="bg-purple-500/10 text-purple-400 p-4 rounded-2xl w-fit mx-auto mb-4">
              <BookOpen className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">No sagas yet</h3>
            <p className="text-sm text-gray-500 mb-6">Forge your first story and begin an interactive adventure.</p>
            <button
              onClick={onNewStory}
              className="bg-gradient-to-r from-purple-600 to-blue-600 text-white font-bold px-6 py-3 rounded-lg touch-manipulation active:scale-95"
            >
              Create Your First Saga
            </button>
          </div>
        )}

        {stories !== null && stories.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-4xl mx-auto">
            {stories.map(s => (
              <button
                key={s.id}
                onClick={() => onOpenStory(s)}
                className="bg-gray-900/60 border border-gray-800 hover:border-purple-500/50 rounded-2xl p-5 text-left transition-all active:scale-95 touch-manipulation"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-bold uppercase tracking-wide text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full">{s.genre}</span>
                  <span className="text-[10px] text-gray-600 flex items-center gap-1"><Clock size={10} /> {timeAgo(s.updated_at)}</span>
                </div>
                <h3 className="text-lg font-semibold text-white truncate">{s.title}</h3>
                <p className="text-sm text-gray-500 line-clamp-2 mt-1">{s.premise}</p>
                <p className="text-xs text-gray-400 mt-3">Day {s.current_day} · {s.time_of_day}</p>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
