import React, { useEffect, useState, useCallback } from "react";
import { X, Backpack, Shield, Sword, Gem, FlaskConical, Package, Scroll } from "lucide-react";
import { fetchInventory, equipItem, unequipItem } from "../utils/api";

const RARITY_STYLE = {
  common: "border-gray-600 text-gray-300",
  uncommon: "border-green-500/40 text-green-300",
  rare: "border-blue-500/40 text-blue-300",
  epic: "border-purple-500/40 text-purple-300",
  legendary: "border-amber-500/40 text-amber-300",
};

const TYPE_ICON = {
  weapon: Sword, armor: Shield, accessory: Gem,
  consumable: FlaskConical, material: Package, quest: Scroll,
};

export default function InventoryPanel({ playthroughId, characters, onClose }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState("");

  const playerId = (characters || []).find(c => c.is_player)?.id || (characters || [])[0]?.id;

  const load = useCallback(async () => {
    const inv = await fetchInventory(playthroughId);
    setData(inv);
  }, [playthroughId]);

  useEffect(() => { load(); }, [load]);

  const bp = (data?.backpacks || []).find(b => b.character_id === playerId);
  const carried = (data?.items || []).filter(i => i.character_id === playerId && !i.equipped);
  const equipped = (data?.equipment || []).filter(e => e.character_id === playerId);
  const bonuses = (data?.bonuses || {})[playerId] || {};
  const bonusText = Object.entries(bonuses).map(([k, v]) => `+${v} ${k}`).join(", ");

  const doEquip = async (itemId) => {
    setBusy(itemId); setMsg("");
    const res = await equipItem(playthroughId, itemId);
    if (!res.ok) setMsg(res.detail);
    await load();
    setBusy(null);
  };

  const doUnequip = async (itemId) => {
    setBusy(itemId); setMsg("");
    const res = await unequipItem(playthroughId, itemId);
    if (!res.ok) setMsg(res.detail);
    await load();
    setBusy(null);
  };

  const cap = bp?.capacity ?? 10;
  const used = bp?.used ?? 0;
  const pct = Math.max(0, Math.min(100, (used / cap) * 100));
  const barColor = pct >= 100 ? "bg-red-500" : pct >= 75 ? "bg-amber-500" : "bg-green-500";

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-gray-900 border-t border-gray-700 rounded-t-2xl max-h-[75dvh] flex flex-col animate-fade-in">
        <header className="flex items-center gap-2 px-4 py-3 border-b border-gray-800 flex-shrink-0">
          <Backpack size={18} className="text-amber-400" />
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-white">Backpack · Level {bp?.level ?? 1}</h3>
            <p className="text-[11px] text-gray-500">Equipped items weigh nothing</p>
          </div>
          <button onClick={onClose} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
            <X size={18} />
          </button>
        </header>

        <div className="px-4 py-3 border-b border-gray-800 flex-shrink-0">
          <div className="flex items-center justify-between text-[11px] text-gray-400 mb-1">
            <span>Load</span>
            <span className={used >= cap ? "text-red-400 font-bold" : ""}>{used}/{cap}</span>
          </div>
          <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
            <div className={`h-full ${barColor} transition-all duration-500`} style={{ width: `${pct}%` }} />
          </div>
          {bonusText && (
            <p className="text-[11px] text-emerald-400 mt-2">Gear bonuses: {bonusText}</p>
          )}
          {msg && <p className="text-[11px] text-red-400 mt-2">{msg}</p>}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          <section>
            <h4 className="text-[10px] uppercase tracking-wide text-gray-500 font-bold mb-2">Equipped</h4>
            {equipped.length === 0 ? (
              <p className="text-xs text-gray-600">Nothing equipped yet.</p>
            ) : (
              <ul className="space-y-2">
                {equipped.map(e => (
                  <li key={e.id} className={`flex items-center gap-2 px-3 py-2 rounded-xl border bg-gray-800/50 ${RARITY_STYLE[e.rarity] || RARITY_STYLE.common}`}>
                    <span className="text-[10px] uppercase text-gray-500 w-16 flex-shrink-0">{e.slot.replace("_", " ")}</span>
                    <span className="flex-1 text-xs truncate">{e.item_name} <span className="text-gray-500">lv{e.item_level}</span></span>
                    <button
                      onClick={() => doUnequip(e.item_id)}
                      disabled={busy === e.item_id}
                      className="px-3 min-h-[44px] rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-200 text-[11px] font-medium touch-manipulation active:scale-95 disabled:opacity-50"
                    >
                      {busy === e.item_id ? "…" : "Unequip"}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h4 className="text-[10px] uppercase tracking-wide text-gray-500 font-bold mb-2">Carried</h4>
            {carried.length === 0 ? (
              <p className="text-xs text-gray-600">Pack is empty — adventure to find loot.</p>
            ) : (
              <ul className="space-y-2">
                {carried.map(i => {
                  const Icon = TYPE_ICON[i.item_type] || Package;
                  const equippable = !!i.slot;
                  return (
                    <li key={i.id} className={`flex items-center gap-2 px-3 py-2 rounded-xl border bg-gray-800/50 ${RARITY_STYLE[i.rarity] || RARITY_STYLE.common}`}>
                      <Icon size={14} className="flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs truncate">{i.name}{i.quantity > 1 ? ` ×${i.quantity}` : ""}</p>
                        <p className="text-[10px] text-gray-500">
                          {i.item_type} · lv{i.item_level} · w{i.weight} · {i.rarity}
                        </p>
                      </div>
                      {equippable && (
                        <button
                          onClick={() => doEquip(i.id)}
                          disabled={busy === i.id}
                          className="px-3 min-h-[44px] rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-[11px] font-medium touch-manipulation active:scale-95 disabled:opacity-50"
                        >
                          {busy === i.id ? "…" : "Equip"}
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
