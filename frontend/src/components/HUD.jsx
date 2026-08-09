import React, { useState } from "react";
import { Heart, Sparkles, MapPin, Backpack } from "lucide-react";
import InventoryPanel from "./InventoryPanel";

export default function HUD({ storyContext }) {
  const [invOpen, setInvOpen] = useState(false);

  if (!storyContext || !storyContext.characters) return null;

  const player = storyContext.characters.find(c => c.is_player) || storyContext.characters[0];
  if (!player) return null;

  const meta = player.metadata || {};
  const stats = meta.stats || {};
  const inventory = Array.isArray(meta.inventory) ? meta.inventory : [];
  const location = storyContext.current_location || "Unknown Realm";

  const hp = stats.Health ?? 100;
  const maxHp = stats.MaxHealth ?? 100;
  const mana = stats.Mana ?? 50;
  const maxMana = stats.MaxMana ?? 50;

  const hpPct = Math.max(0, Math.min(100, (hp / maxHp) * 100));
  const manaPct = Math.max(0, Math.min(100, (mana / maxMana) * 100));

  return (
    <>
      <div className="bg-gray-800/80 backdrop-blur-sm border-b border-gray-700 px-3 sm:px-4 py-2 flex flex-wrap items-center gap-3 touch-manipulation">
        {/* Location */}
        <div className="flex items-center gap-1.5 text-xs sm:text-sm text-blue-300 min-w-[100px]">
          <MapPin size={14} className="text-blue-400" />
          <span className="truncate font-medium">{location}</span>
        </div>

        {/* Bars Container */}
        <div className="flex flex-1 min-w-[150px] max-w-[300px] gap-2">
          <div className="flex-1 flex flex-col min-w-[60px]">
            <div className="flex items-center gap-1 text-[10px] sm:text-xs text-red-400 mb-0.5">
              <Heart size={10} /> <span>HP</span>
            </div>
            <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-red-500 transition-all duration-500" style={{ width: `${hpPct}%` }} />
            </div>
            <span className="text-[9px] text-gray-500 mt-0.5 text-right">{Math.round(hp)}/{maxHp}</span>
          </div>

          <div className="flex-1 flex flex-col min-w-[60px]">
            <div className="flex items-center gap-1 text-[10px] sm:text-xs text-blue-400 mb-0.5">
              <Sparkles size={10} /> <span>MP</span>
            </div>
            <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 transition-all duration-500" style={{ width: `${manaPct}%` }} />
            </div>
            <span className="text-[9px] text-gray-500 mt-0.5 text-right">{Math.round(mana)}/{maxMana}</span>
          </div>
        </div>

        {/* Stat Chips */}
        <div className="hidden sm:flex items-center gap-1.5">
          {Object.entries(stats).filter(([k]) => !["Health", "MaxHealth", "Mana", "MaxMana"].includes(k)).slice(0, 2).map(([k, v]) => (
            <span key={k} className="px-1.5 py-0.5 bg-gray-700 text-gray-300 rounded text-[10px] font-medium border border-gray-600">
              {k}: {v}
            </span>
          ))}
        </div>

        {/* Backpack (44px tap target) */}
        <button
          onClick={() => setInvOpen(true)}
          className="flex items-center gap-1 text-[10px] sm:text-xs text-amber-400 min-h-[44px] min-w-[44px] justify-center rounded-xl hover:bg-gray-700/50 touch-manipulation active:scale-95"
          title="Open backpack"
        >
          <Backpack size={14} />
          <span>{inventory.length}</span>
        </button>
      </div>

      {invOpen && (
        <InventoryPanel
          playthroughId={storyContext.playthrough_id}
          characters={storyContext.characters}
          onClose={() => setInvOpen(false)}
        />
      )}
    </>
  );
}
