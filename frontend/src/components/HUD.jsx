import React, { useState } from "react";
import { Heart, Sparkles, MapPin, Backpack, Map as MapIcon, UserRound, Coins } from "lucide-react";
import InventoryPanel from "./InventoryPanel";
import StoryMap from "./StoryMap";
import CharacterSheet from "./CharacterSheet";

export default function HUD({ storyContext }) {
  const [invOpen, setInvOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);

  if (!storyContext || !storyContext.characters) return null;

  const player = storyContext.characters.find(c => c.is_player) || storyContext.characters[0];
  if (!player) return null;

  const meta = player.metadata || {};
  const stats = meta.stats || {};
  const inventory = Array.isArray(meta.inventory) ? meta.inventory : [];
  const location = storyContext.current_location || "Unknown Realm";
  const currency = storyContext.currency ?? 0;

  const hp = stats.Health ?? 100;
  const maxHp = stats.MaxHealth ?? 100;
  const mana = stats.Mana ?? 50;
  const maxMana = stats.MaxMana ?? 50;

  const hpPct = Math.max(0, Math.min(100, (hp / maxHp) * 100));
  const manaPct = Math.max(0, Math.min(100, (mana / maxMana) * 100));

  return (
    <>
      <div className="bg-gray-900 border-b border-gray-800 px-3 py-3 space-y-3">
        <div className="flex items-center justify-between text-xs">
          <button onClick={() => setMapOpen(true)} className="flex items-center gap-1.5 text-blue-300 truncate max-w-[60%] hover:text-blue-200">
            <MapPin size={14} className="flex-shrink-0" />
            <span className="truncate font-medium">{location}</span>
          </button>
          <div className="flex items-center gap-1 text-amber-400 font-bold">
            <Coins size={14} />
            <span>{currency}</span>
          </div>
        </div>

        <div className="flex gap-3">
          <div className="flex-1 flex flex-col">
            <div className="flex items-center justify-between text-[10px] text-red-400 mb-0.5">
              <div className="flex items-center gap-1"><Heart size={10} /> HP</div>
              <span>{Math.round(hp)}/{maxHp}</span>
            </div>
            <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-red-500 transition-all duration-500" style={{ width: `${hpPct}%` }} />
            </div>
          </div>
          <div className="flex-1 flex flex-col">
            <div className="flex items-center justify-between text-[10px] text-blue-400 mb-0.5">
              <div className="flex items-center gap-1"><Sparkles size={10} /> MP</div>
              <span>{Math.round(mana)}/{maxMana}</span>
            </div>
            <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 transition-all duration-500" style={{ width: `${manaPct}%` }} />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {Object.entries(stats).filter(([k]) => !["Health", "MaxHealth", "Mana", "MaxMana"].includes(k)).slice(0, 3).map(([k, v]) => (
            <span key={k} className="px-1.5 py-0.5 bg-gray-800 text-gray-300 rounded text-[9px] font-medium border border-gray-700">
              {k}: {v}
            </span>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button onClick={() => setSheetOpen(true)} className="flex-1 flex items-center justify-center gap-1 text-purple-300 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-[11px] font-medium touch-manipulation" title="Character sheet">
            <UserRound size={14} /> Sheet
          </button>
          <button onClick={() => setMapOpen(true)} className="flex-1 flex items-center justify-center gap-1 text-blue-300 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-[11px] font-medium touch-manipulation" title="World map">
            <MapIcon size={14} /> Map
          </button>
          <button onClick={() => setInvOpen(true)} className="flex-1 flex items-center justify-center gap-1 text-amber-400 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-[11px] font-medium touch-manipulation" title="Open backpack">
            <Backpack size={14} /> Pack
          </button>
        </div>
      </div>

      {invOpen && <InventoryPanel playthroughId={storyContext.playthrough_id} characters={storyContext.characters} onClose={() => setInvOpen(false)} />}
      {mapOpen && <StoryMap playthroughId={storyContext.playthrough_id} onClose={() => setMapOpen(false)} />}
      {sheetOpen && <CharacterSheet storyContext={storyContext} onClose={() => setSheetOpen(false)} />}
    </>
  );
}
