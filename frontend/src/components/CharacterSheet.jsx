import React, { useEffect, useState } from "react";
import { X, UserRound, Sparkles, Shield } from "lucide-react";
import { fetchInventory } from "../utils/api";

export default function CharacterSheet({ storyContext, onClose }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (storyContext?.playthrough_id) fetchInventory(storyContext.playthrough_id).then(setData);
  }, [storyContext?.playthrough_id]);

  const player = (storyContext?.characters || []).find(c => c.is_player) || (storyContext?.characters || [])[0];
  if (!player) return null;

  const meta = player.metadata || {};
  const stats = meta.stats || {};
  const abilities = (data?.abilities || {})[player.id] || meta.abilities || [];
  const bonuses = (data?.bonuses || {})[player.id] || {};
  const equipped = (data?.equipment || []).filter(e => e.character_id === player.id);

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-gray-900 border-t border-gray-700 rounded-t-2xl max-h-[80dvh] flex flex-col animate-fade-in">
        <header className="flex items-center gap-2 px-4 py-3 border-b border-gray-800 flex-shrink-0">
          <UserRound size={18} className="text-purple-400" />
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-white truncate">{player.character_name}</h3>
            <p className="text-[11px] text-gray-500 truncate">{player.role}</p>
          </div>
          <button onClick={onClose} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          {player.background && (
            <p className="text-xs text-gray-400 leading-relaxed">{player.background}</p>
          )}

          <section>
            <h4 className="text-[10px] uppercase tracking-wide text-gray-500 font-bold mb-2">Stats</h4>
            <ul className="space-y-1.5">
              {Object.entries(stats).map(([k, v]) => {
                const b = Math.round(bonuses[k] || 0);
                return (
                  <li key={k} className="flex items-center justify-between px-3 py-2 rounded-xl bg-gray-800/50 border border-gray-700">
                    <span className="text-xs text-gray-300">{k}</span>
                    <span className="text-xs font-semibold text-white">
                      {Math.round(v)}{b > 0 && <span className="text-emerald-400 ml-1">(+{b})</span>}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>

          <section>
            <h4 className="text-[10px] uppercase tracking-wide text-violet-400 font-bold mb-2 flex items-center gap-1">
              <Sparkles size={12} /> Abilities
            </h4>
            {abilities.length === 0 ? (
              <p className="text-xs text-gray-600">None yet.</p>
            ) : (
              <ul className="space-y-2">
                {abilities.map((a, i) => (
                  <li key={i} className="px-3 py-2 rounded-xl border border-violet-500/40 bg-violet-500/10">
                    <p className="text-xs font-semibold text-violet-300">{a?.name}</p>
                    {a?.description && <p className="text-[11px] text-gray-400 mt-0.5">{a.description}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h4 className="text-[10px] uppercase tracking-wide text-gray-500 font-bold mb-2 flex items-center gap-1">
              <Shield size={12} /> Equipped
            </h4>
            {equipped.length === 0 ? (
              <p className="text-xs text-gray-600">Nothing equipped.</p>
            ) : (
              <ul className="space-y-1.5">
                {equipped.map(e => (
                  <li key={e.id} className="flex items-center justify-between px-3 py-2 rounded-xl bg-gray-800/50 border border-gray-700">
                    <span className="text-xs text-gray-300 truncate">{e.item_name}</span>
                    <span className="text-[10px] uppercase text-gray-500">{e.slot.replace("_", " ")}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
