import React, { useState, useEffect, useCallback, useMemo } from "react";
import { X, Backpack, Shield, Sword, Gem, FlaskConical, Package, Scroll, Sparkles, Trash2 } from "lucide-react";
import { fetchInventory, equipItem, unequipItem, useItem, dropItem } from "../utils/api";

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
    setData(await fetchInventory(playthroughId));
  }, [playthroughId]);

  useEffect(() => { load(); }, [load]);

  const bp = (data?.backpacks || []).find(b => b.character_id === playerId);
  const carried = (data?.items || []).filter(i => i.character_id === playerId && !i.equipped);
  const equipped = (data?.equipment || []).filter(e => e.character_id === playerId);
  const abilities = (data?.abilities || {})[playerId] || [];
  const bonuses = (data?.bonuses || {})[playerId] || {};
  const bonusText = Object.entries(bonuses).map(([k, v]) => `+${v} ${k}`).join(", ");

  const groupedCarried = useMemo(() => {
    const map = new Map();
    carried.forEach(i => {
      const key = i.name;
      if (!map.has(key)) {
        map.set(key, { ...i, quantity: 0, ids: [] });
      }
      const entry = map.get(key);
      entry.quantity += i.quantity;
      entry.ids.push(i.id);
      if (i.metadata?.description) entry.metadata = i.metadata;
      if (i.metadata?.use_effect) entry.metadata = { ...entry.metadata, use_effect: i.metadata.use_effect };
    });
    return Array.from(map.values());
  }, [carried]);

  const totalItemCount = useMemo(() => {
    return groupedCarried.reduce((sum, item) => sum + item.quantity, 0);
  }, [groupedCarried]);

  const runAction = async (actionFn, actionName, itemId, extraData) => {
    setBusy(itemId); setMsg("");
    
    setData(prev => {
      if (!prev) return prev;
      const next = { ...prev, items: prev.items.map(i => ({...i})), equipment: prev.equipment.map(e => ({...e})) };
      const itemIdx = next.items.findIndex(i => i.id === itemId);
      if (itemIdx === -1 && actionName !== 'unequip') return prev;
      
      if (actionName === 'drop') {
        next.items = next.items.filter(i => i.id !== itemId);
      } else if (actionName === 'use') {
        if (next.items[itemIdx].quantity > 1) {
          next.items[itemIdx].quantity -= 1;
        } else {
          next.items.splice(itemIdx, 1);
        }
      } else if (actionName === 'equip') {
        const item = next.items[itemIdx];
        next.items.splice(itemIdx, 1);
        next.equipment.push({ id: 'temp', character_id: item.character_id, item_id: item.id, slot: item.slot, item_name: item.name, rarity: item.rarity, item_level: item.item_level });
      } else if (actionName === 'unequip') {
        const eqIdx = next.equipment.findIndex(e => e.item_id === itemId);
        if (eqIdx !== -1) {
          const eq = next.equipment[eqIdx];
          next.equipment.splice(eqIdx, 1);
          const origItem = data.items.find(i => i.id === itemId);
          if (origItem) next.items.push({...origItem});
        }
      }
      return next;
    });

    const res = await actionFn(playthroughId, itemId);
    if (!res.ok) {
      setMsg(res.detail);
      await load();
    }
    setBusy(null);
  };

  const cap = bp?.capacity ?? 10;
  const used = bp?.used ?? 0;
  const pct = Math.max(0, Math.min(100, (used / cap) * 100));
  const barColor = pct >= 100 ? "bg-red-500" : pct >= 75 ? "bg-amber-500" : "bg-green-500";

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-gray-900 border-t border-gray-700 rounded-t-2xl max-h-[85dvh] flex flex-col animate-fade-in">
        <header className="flex items-center gap-2 px-4 py-3 border-b border-gray-800 flex-shrink-0">
          <Backpack size={18} className="text-amber-400" />
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-white">Backpack · Level {bp?.level ?? 1}</h3>
            <p className="text-[11px] text-gray-500">Items: {totalItemCount} · Load: {used}/{cap}</p>
          </div>
          <button onClick={onClose} className="p-2.5 rounded-xl hover:bg-gray-800 text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation">
            <X size={18} />
          </button>
        </header>

        <div className="px-4 py-3 border-b border-gray-800 flex-shrink-0">
          <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
            <div className={`h-full ${barColor} transition-all duration-500`} style={{ width: `${pct}%` }} />
          </div>
          {bonusText && <p className="text-[11px] text-emerald-400 mt-2">Gear bonuses: {bonusText}</p>}
          {msg && <p className="text-[11px] text-red-400 mt-2">{msg}</p>}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          <section>
            <h4 className="text-[10px] uppercase tracking-wide text-violet-400 font-bold mb-2 flex items-center gap-1">
              <Sparkles size={12} /> Abilities
            </h4>
            {abilities.length === 0 ? (
              <p className="text-xs text-gray-600">No abilities learned yet.</p>
            ) : (
              <ul className="space-y-2">
                {abilities.map((a, i) => (
                  <li key={`${a?.name}-${i}`} className="px-3 py-2 rounded-xl border border-violet-500/40 bg-violet-500/10">
                    <p className="text-xs font-semibold text-violet-300">{a?.name}</p>
                    {a?.description && <p className="text-[11px] text-gray-400 mt-0.5">{a.description}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>

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
                    <button onClick={() => runAction(unequipItem, 'unequip', e.item_id)} disabled={busy === e.item_id}
                      className="px-3 min-h-[44px] rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-200 text-[11px] font-medium touch-manipulation active:scale-95 disabled:opacity-50">
                      {busy === e.item_id ? "…" : "Unequip"}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h4 className="text-[10px] uppercase tracking-wide text-gray-500 font-bold mb-2">Carried</h4>
            {groupedCarried.length === 0 ? (
              <p className="text-xs text-gray-600">Pack is empty.</p>
            ) : (
              <ul className="space-y-2">
                {groupedCarried.map(i => {
                  const Icon = TYPE_ICON[i.item_type] || Package;
                  const desc = i.metadata?.description;
                  const useEffect = i.metadata?.use_effect;
                  return (
                    <li key={i.name} className={`px-3 py-2 rounded-xl border bg-gray-800/50 ${RARITY_STYLE[i.rarity] || RARITY_STYLE.common}`}>
                      <div className="flex items-start gap-2">
                        <Icon size={14} className="flex-shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs truncate font-semibold">{i.name}{i.quantity > 1 ? ` ×${i.quantity}` : ""}</p>
                          <p className="text-[10px] text-gray-500">{i.item_type} · lv{i.item_level} · w{i.weight} · {i.rarity}</p>
                          {desc && <p className="text-[10px] text-gray-400 mt-0.5">{desc}</p>}
                          {useEffect && <p className="text-[10px] text-emerald-400 mt-1 italic">Effect: {useEffect}</p>}
                        </div>
                      </div>
                      <div className="flex gap-2 mt-2">
                        {i.slot && (
                          <button onClick={() => runAction(equipItem, 'equip', i.ids[0])} disabled={busy === i.ids[0]}
                            className="flex-1 min-h-[44px] rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-[11px] font-medium touch-manipulation active:scale-95 disabled:opacity-50">
                            {busy === i.ids[0] ? "…" : "Equip"}
                          </button>
                        )}
                        {i.item_type === "consumable" && (
                          <button onClick={() => runAction(useItem, 'use', i.ids[0])} disabled={busy === i.ids[0]}
                            className="flex-1 min-h-[44px] rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-medium touch-manipulation active:scale-95 disabled:opacity-50">
                            {busy === i.ids[0] ? "…" : "Use"}
                          </button>
                        )}
                        {i.item_type !== "quest" && (
                          <button onClick={() => runAction(dropItem, 'drop', i.ids[0])} disabled={busy === i.ids[0]}
                            className="px-3 min-h-[44px] rounded-lg bg-gray-700 hover:bg-red-600/60 text-gray-300 text-[11px] touch-manipulation active:scale-95 disabled:opacity-50">
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
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
