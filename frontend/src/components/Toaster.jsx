import React, { useEffect, useState } from 'react';
import { CheckCircle2, AlertCircle, Info } from 'lucide-react';
import { subscribeToast } from '../utils/toast';

export default function Toaster() {
  const [items, setItems] = useState([]);

  useEffect(() => subscribeToast(item => {
    setItems(prev => [...prev.slice(-3), item]);
    setTimeout(() => setItems(prev => prev.filter(t => t.id !== item.id)), 3500);
  }), []);

  if (!items.length) return null;

  const icon = (k) => k === 'success'
    ? <CheckCircle2 size={15} className="text-emerald-400 flex-shrink-0" />
    : k === 'error'
      ? <AlertCircle size={15} className="text-red-400 flex-shrink-0" />
      : <Info size={15} className="text-blue-400 flex-shrink-0" />;

  return (
    <div className="fixed top-3 left-1/2 -translate-x-1/2 z-[100] space-y-2 w-[calc(100%-24px)] max-w-sm pointer-events-none">
      {items.map(t => (
        <div
          key={t.id}
          className={`flex items-center gap-2 px-4 py-3 rounded-xl border text-sm shadow-xl animate-fade-in pointer-events-auto ${
            t.kind === 'error'
              ? 'bg-red-950/95 border-red-500/40 text-red-200'
              : t.kind === 'success'
                ? 'bg-emerald-950/95 border-emerald-500/40 text-emerald-100'
                : 'bg-gray-900/95 border-gray-700 text-gray-200'
          }`}
        >
          {icon(t.kind)}
          <span className="flex-1 leading-snug">{t.message}</span>
        </div>
      ))}
    </div>
  );
}
