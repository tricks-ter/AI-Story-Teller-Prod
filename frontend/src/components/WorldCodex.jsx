import React, { useEffect, useState } from 'react';
import { X, ScrollText, Crown, Users, MapPin, Skull } from 'lucide-react';
import { BASE_URL, authHeaders, parseJsonSafe } from '../utils/auth';

function statusTone(status) {
  const s = String(status || '').toLowerCase();
  if (/(war|hostile|ruin|famine|disgrac|dead|burn|siege)/.test(s)) return 'text-red-400 bg-red-500/10 border-red-500/30';
  if (/(prosper|rising|thriv|friendly|triumph|golden|peace|ally)/.test(s)) return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
  if (/(tense|unrest|plot|scheme|wary|recover)/.test(s)) return 'text-amber-400 bg-amber-500/10 border-amber-500/30';
  return 'text-gray-400 bg-gray-700/30 border-gray-600/40';
}

function NodeCard({ n }) {
  const rel = Number(n.relationship || 0);
  return (
    <div className={`bg-gray-900/70 border border-gray-800 rounded-xl p-3 ${n.is_alive === false ? 'opacity-60' : ''}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-white truncate flex items-center gap-1.5">
          {n.is_alive === false && <Skull size={12} className="text-gray-500" />}
          {n.name}
        </span>
        <span className={`text-[10px] px-2 py-0.5 rounded-full border whitespace-nowrap ${statusTone(n.status)}`}>{n.status || 'stable'}</span>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5 text-[11px] text-gray-400">
        <span className="uppercase text-[9px] font-bold text-purple-400">{n.node_type}</span>
        {n.node_type === 'npc' ? (
          <span className={rel > 0 ? 'text-emerald-400' : rel < 0 ? 'text-red-400' : ''}>relationship {rel > 0 ? `+${rel}` : rel}</span>
        ) : (
          <>
            <span>power {Number(n.power || 0)}</span>
            <span>wealth {Number(n.wealth || 0)}</span>
          </>
        )}
        {n.allegiance ? <span className="text-blue-300">⚑ {n.allegiance}</span> : null}
      </div>
    </div>
  );
}

export default function WorldCodex({ playthroughId, onClose }) {
  const [nodes, setNodes] = useState(null);
  const [events, setEvents] = useState([]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [nr, er] = await Promise.all([
          fetch(`${BASE_URL}/playthroughs/${playthroughId}/world-nodes`, { headers: authHeaders() }),
          fetch(`${BASE_URL}/playthroughs/${playthroughId}/world-events`, { headers: authHeaders() }),
        ]);
        const nd = nr.ok ? await parseJsonSafe(nr) : [];
        const ev = er.ok ? await parseJsonSafe(er) : [];
        if (!alive) return;
        setNodes(Array.isArray(nd) ? nd : []);
        setEvents(Array.isArray(ev) ? ev : []);
      } catch {
        if (alive) setNodes([]);
      }
    })();
    return () => { alive = false; };
  }, [playthroughId]);

  const powers = (nodes || []).filter(n => ['region', 'faction', 'economy_state'].includes(n.node_type));
  const places = (nodes || []).filter(n => ['settlement', 'location'].includes(n.node_type));
  const people = (nodes || []).filter(n => n.node_type === 'npc');

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center" onClick={onClose}>
      <div
        className="bg-gray-950 border border-gray-800 w-full sm:max-w-lg h-[85dvh] sm:h-[75dvh] rounded-t-2xl sm:rounded-2xl flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800 flex-shrink-0">
          <ScrollText size={16} className="text-purple-400" />
          <h3 className="text-sm font-semibold text-white flex-1">World Codex</h3>
          <button onClick={onClose} className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-xl hover:bg-gray-800 text-gray-400 touch-manipulation">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          {nodes === null && <p className="text-center text-gray-500 text-sm mt-10">Reading the chronicles…</p>}

          {nodes !== null && nodes.length === 0 && (
            <div className="text-center mt-12 px-6">
              <div className="bg-purple-500/10 text-purple-400 p-4 rounded-2xl w-fit mx-auto mb-3"><ScrollText className="w-7 h-7" /></div>
              <p className="text-sm text-gray-400">The world awakens as you explore. Kingdoms, noble houses and people you meet will be recorded here — with their living state.</p>
            </div>
          )}

          {powers.length > 0 && (
            <section>
              <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-purple-300 mb-2"><Crown size={12} /> Kingdoms & Houses</h4>
              <div className="space-y-2">{powers.map(n => <NodeCard key={n.id} n={n} />)}</div>
            </section>
          )}

          {places.length > 0 && (
            <section>
              <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-blue-300 mb-2"><MapPin size={12} /> Settlements & Places</h4>
              <div className="space-y-2">{places.map(n => <NodeCard key={n.id} n={n} />)}</div>
            </section>
          )}

          {people.length > 0 && (
            <section>
              <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-emerald-300 mb-2"><Users size={12} /> People</h4>
              <div className="space-y-2">{people.map(n => <NodeCard key={n.id} n={n} />)}</div>
            </section>
          )}

          <section>
            <h4 className="text-[11px] font-bold uppercase tracking-wide text-amber-300 mb-2">Chronicle of Events</h4>
            {events.length === 0 ? (
              <p className="text-xs text-gray-600">No recorded events yet.</p>
            ) : (
              <div className="space-y-1.5">
                {events.map(e => (
                  <p key={e.id} className="text-xs text-gray-400 leading-relaxed">
                    <span className="text-amber-400 font-semibold">Day {e.day}</span>
                    <span className="text-gray-600"> · {e.event_type} · </span>
                    {e.description} <span className="text-gray-500">({e.node_name})</span>
                  </p>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
