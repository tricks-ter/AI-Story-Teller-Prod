import React, { useEffect, useState, useCallback } from "react";
import { X, Map as MapIcon, MapPin } from "lucide-react";
import { fetchMap } from "../utils/api";

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "Just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function StoryMap({ playthroughId, onClose }) {
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    const m = await fetchMap(playthroughId);
    setData(m);
    if (m?.locations?.length && !selected) {
      setSelected(m.locations.find(l => l.is_current) || m.locations[m.locations.length - 1]);
    }
  }, [playthroughId]);

  useEffect(() => { load(); }, [load]);

  const locs = data?.locations || [];
  const sel = locs.find(l => l.id === selected?.id) || selected;

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-gray-900 border-t border-gray-700 rounded-t-2xl max-h-[80dvh] flex flex-col animate-fade-in">
        <header className="flex items-center gap-2 px-4 py-3 border-b border-gray-800 flex-shrink-0">
          <MapIcon size={18} className="text-blue-400" />
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-white">World Map</h3>
            <p className="text-[11px] text-gray-500">{locs.length} place{locs.length === 1 ? "" : "s"} discovered</p>
          </div>
          <button onClick={onClose} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4">
          {locs.length === 0 ? (
            <p className="text-xs text-gray-600 text-center py-8">The map is blank — your journey will chart it.</p>
          ) : (
            <div className="flex gap-4">
              {/* Journey line */}
              <div className="flex-1 min-w-0">
                <ol className="relative border-l border-gray-700 ml-3 space-y-1">
                  {locs.map(l => (
                    <li key={l.id} className="relative pl-6">
                      <button
                        onClick={() => setSelected(l)}
                        className="w-full text-left px-2 py-2.5 rounded-xl touch-manipulation active:scale-95 min-h-[44px] flex items-center gap-2"
                      >
                        <span className={`absolute -left-[9px] w-4 h-4 rounded-full border-2 ${
                          l.is_current ? "bg-purple-500 border-purple-300 animate-pulse" :
                          sel?.id === l.id ? "bg-blue-500 border-blue-300" : "bg-gray-700 border-gray-600"}`} />
                        <span className={`text-xs truncate ${l.is_current ? "text-purple-300 font-semibold" : "text-gray-300"}`}>
                          {l.name}
                        </span>
                        {l.is_current && <span className="text-[9px] uppercase text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded-full">now</span>}
                      </button>
                    </li>
                  ))}
                </ol>
              </div>

              {/* Detail pane */}
              <div className="w-[45%] flex-shrink-0">
                {sel && (
                  <div className="sticky top-0 bg-gray-800/60 border border-gray-700 rounded-xl p-3">
                    <p className="text-xs font-semibold text-white flex items-center gap-1.5 mb-2">
                      <MapPin size={12} className="text-blue-400" /> {sel.name}
                    </p>
                    <p className="text-[11px] text-gray-400 leading-relaxed mb-3">
                      {sel.description || "No chronicle recorded yet."}
                    </p>
                    <div className="space-y-1 text-[10px] text-gray-500">
                      <p>Visits: <span className="text-gray-300">{sel.visit_count ?? 1}</span></p>
                      <p>Discovered: <span className="text-gray-300">{timeAgo(sel.created_at)}</span></p>
                      <p>Last here: <span className="text-gray-300">{timeAgo(sel.last_visited_at || sel.created_at)}</span></p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
