import React, { useState, useEffect, useRef } from 'react';
import { ArrowLeft, Wand2, Globe, Lock, X, ImageIcon } from 'lucide-react';
import { fileToDataUrl } from '../utils/art';

const GENRES = ['Fantasy', 'Sci-Fi', 'Cyberpunk', 'Lovecraftian Horror', 'Modern Slice of Life', 'Mystery', 'Post-Apocalyptic', 'Historical', 'Wuxia'];

function ImageField({ label, value, onChange, hint }) {
  const ref = useRef(null);
  const pick = async (file) => {
    if (!file) return;
    try { onChange(await fileToDataUrl(file)); } catch (e) { console.warn('[art]', e); }
  };
  return (
    <div>
      <label className="block text-sm font-medium text-gray-400 mb-2">{label}</label>
      <div className="flex items-center gap-3">
        <div className="w-20 h-14 rounded-lg overflow-hidden bg-gray-800 border border-gray-700 flex items-center justify-center flex-shrink-0">
          {value ? <img src={value} alt={label} className="w-full h-full object-cover" /> : <ImageIcon size={16} className="text-gray-600" />}
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => ref.current?.click()} className="px-3 min-h-[44px] rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium touch-manipulation active:scale-95">Choose</button>
          {value && (
            <button type="button" onClick={() => onChange('')} className="px-3 min-h-[44px] rounded-lg bg-gray-800 hover:bg-red-600/40 text-gray-300 text-xs touch-manipulation active:scale-95"><X size={13} /></button>
          )}
        </div>
      </div>
      {hint && <p className="text-[11px] text-gray-600 mt-1">{hint}</p>}
      <input ref={ref} type="file" accept="image/*" className="hidden" onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; pick(f); }} />
    </div>
  );
}

export default function StoryCreator({ onStart, onBack, initialData, isEditing, onUpdate }) {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState({
    title: '', genre: 'Fantasy', premise: '', starterLocation: '', tone: '', isPublic: true,
    coverImage: '', bannerImage: '',
    characterName: '', characterRole: 'Protagonist', characterBackground: '', characterImage: '', characterId: ''
  });

  useEffect(() => {
    if (!initialData) return;
    const pc = (initialData.characters || []).find(c => c.is_player) || (initialData.characters || [])[0];
    setData(prev => ({
      ...prev,
      title: initialData.title || '',
      genre: initialData.genre || 'Fantasy',
      premise: initialData.premise || '',
      starterLocation: initialData.metadata?.starter_location || '',
      tone: initialData.metadata?.tone || '',
      isPublic: initialData.is_public ?? true,
      coverImage: initialData.cover_image || '',
      bannerImage: initialData.banner_image || '',
      characterName: pc?.name || '',
      characterRole: pc?.role || 'Protagonist',
      characterBackground: pc?.background || '',
      characterImage: pc?.image || '',
      characterId: pc?.id || ''
    }));
  }, [initialData]);

  const set = (k, v) => setData(d => ({ ...d, [k]: v }));
  const inputCls = "w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-base text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none";

  const handleFinish = () => {
    setBusy(true);
    if (isEditing && onUpdate && initialData) onUpdate(initialData.id, data);
    else onStart(data);
  };

  return (
    <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col items-center p-4">
      <div className="my-auto w-full max-w-2xl bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl p-5 md:p-8 relative my-6">
        <button onClick={onBack} className="absolute top-3 left-3 md:top-4 md:left-4 text-gray-500 hover:text-white flex items-center gap-2 text-sm min-h-[44px] min-w-[44px] justify-center touch-manipulation">
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="text-center mb-6 md:mb-8 pt-8 md:pt-0">
          <h2 className="text-2xl md:text-3xl font-bold text-white mb-2">{isEditing ? 'Edit Your Saga' : 'Forge Your Saga'}</h2>
          <div className="h-1 w-24 bg-purple-500 mx-auto rounded-full"></div>
          <p className="text-xs text-gray-500 mt-2">Step {step} of 3 — {step === 1 ? 'World & Visibility' : step === 2 ? 'Protagonist' : 'Review'}</p>
        </div>

        {step === 1 && (
          <div className="space-y-5 md:space-y-6 animate-fade-in">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Story Title</label>
              <input type="text" placeholder="e.g., The Clockwork Crown" className={inputCls} value={data.title} onChange={e => set('title', e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Genre</label>
              <select className={inputCls} value={data.genre} onChange={e => set('genre', e.target.value)}>
                {GENRES.map(g => <option key={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">The Premise</label>
              <textarea placeholder="Describe the world and the initial conflict..." rows="4" className={`${inputCls} resize-none`} value={data.premise} onChange={e => set('premise', e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Starting Location <span className="text-gray-600">(optional)</span></label>
              <input type="text" placeholder="e.g., The port city of Vhal" className={inputCls} value={data.starterLocation} onChange={e => set('starterLocation', e.target.value)} />
              <p className="text-[11px] text-gray-600 mt-1">Every new journey begins here and the world map is seeded with it.</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Tone & Style Direction <span className="text-gray-600">(optional)</span></label>
              <textarea placeholder="e.g., Gritty and political; keep magic rare and costly." rows="2" className={`${inputCls} resize-none`} value={data.tone} onChange={e => set('tone', e.target.value)} />
            </div>
            <div className="flex items-center justify-between bg-gray-800/50 border border-gray-700 rounded-xl px-4 py-3">
              <span className="flex items-center gap-2 text-sm text-gray-300">
                {data.isPublic ? <Globe size={15} className="text-emerald-400" /> : <Lock size={15} className="text-amber-400" />}
                {data.isPublic ? 'Public — anyone can play' : 'Private — only you'}
              </span>
              <button type="button" onClick={() => set('isPublic', !data.isPublic)} className={`w-12 h-7 rounded-full transition-colors touch-manipulation ${data.isPublic ? 'bg-emerald-600' : 'bg-gray-700'}`}>
                <span className={`block w-5 h-5 bg-white rounded-full transition-transform ${data.isPublic ? 'translate-x-6' : 'translate-x-1'}`} />
              </button>
            </div>
            <ImageField label="Cover Image" value={data.coverImage} onChange={v => set('coverImage', v)} hint="Shown on library cards." />
            <ImageField label="Banner Image" value={data.bannerImage} onChange={v => set('bannerImage', v)} hint="Shown on the story page header." />
            <button onClick={() => setStep(2)} disabled={!data.title} className="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold py-3.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed touch-manipulation active:scale-95">
              Next: Protagonist
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5 md:space-y-6 animate-fade-in">
            {isEditing && (
              <p className="text-[11px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
                Character edits apply to NEW journeys. Existing journeys keep their own copy of the cast.
              </p>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Character Name</label>
              <input type="text" placeholder="Who are you playing?" className={inputCls} value={data.characterName} onChange={e => set('characterName', e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Role / Class</label>
              <input type="text" placeholder="e.g. Exiled Paladin, Rogue Hacker" className={inputCls} value={data.characterRole} onChange={e => set('characterRole', e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Character Background</label>
              <textarea placeholder="What is their history, motivation, or dark secret?" rows="4" className={`${inputCls} resize-none`} value={data.characterBackground} onChange={e => set('characterBackground', e.target.value)} />
            </div>
            <ImageField label="Portrait" value={data.characterImage} onChange={v => set('characterImage', v)} hint="Shown on the story page cast list." />
            <div className="flex gap-3 pt-2">
              <button onClick={() => setStep(1)} className="flex-1 bg-gray-800 hover:bg-gray-700 text-white font-bold py-3.5 rounded-lg touch-manipulation active:scale-95">Back</button>
              <button onClick={() => setStep(3)} disabled={!data.characterName} className="flex-[2] bg-purple-600 hover:bg-purple-700 text-white font-bold py-3.5 rounded-lg disabled:opacity-50 touch-manipulation active:scale-95">Next: Review</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4 animate-fade-in">
            {(data.coverImage || data.bannerImage) && (
              <div className="h-32 rounded-xl overflow-hidden bg-gray-800">
                <img src={data.bannerImage || data.coverImage} alt="banner" className="w-full h-full object-cover" />
              </div>
            )}
            <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4 space-y-1">
              <p className="text-lg font-semibold text-white">{data.title}</p>
              <p className="text-xs text-purple-400">{data.genre} · {data.isPublic ? 'Public' : 'Private'}</p>
              {data.starterLocation && <p className="text-xs text-blue-300">Starts in: {data.starterLocation}</p>}
              {data.tone && <p className="text-xs text-gray-400 italic">Tone: {data.tone}</p>}
              <p className="text-sm text-gray-300 mt-2 leading-relaxed">{data.premise}</p>
            </div>
            <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4 flex items-center gap-3">
              <div className="w-12 h-12 rounded-lg overflow-hidden bg-gray-800 flex items-center justify-center flex-shrink-0">
                {data.characterImage ? <img src={data.characterImage} alt="portrait" className="w-full h-full object-cover" /> : <Wand2 size={16} className="text-purple-400" />}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-white truncate">{data.characterName}</p>
                <p className="text-xs text-gray-500 truncate">{data.characterRole}</p>
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setStep(2)} className="flex-1 bg-gray-800 hover:bg-gray-700 text-white font-bold py-3.5 rounded-lg touch-manipulation active:scale-95">Back</button>
              <button onClick={handleFinish} disabled={busy} className="flex-[2] bg-gradient-to-r from-purple-600 to-blue-600 hover:opacity-90 text-white font-bold py-3.5 rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 touch-manipulation active:scale-95">
                <Wand2 className="w-4 h-4 md:w-5 md:h-5" /> {busy ? 'Saving…' : isEditing ? 'Save Changes' : 'Begin Adventure'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
