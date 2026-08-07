import React, { useState } from 'react';
import { ArrowLeft, Wand2 } from 'lucide-react';

export default function StoryCreator({ onStart, onBack }) {
  const [step, setStep] = useState(1);
  const [data, setData] = useState({
    title: '',
    genre: 'Fantasy',
    premise: '',
    characterName: '',
    characterRole: 'Protagonist',
    characterBackground: ''
  });

  const handleNext = () => setStep(s => s + 1);
  const handleBack = () => setStep(s => s - 1);
  const handleFinish = () => onStart(data);

  return (
    <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex items-center justify-center p-4">
      <div className="max-w-2xl w-full bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl p-5 md:p-8 relative">
        <button onClick={onBack} className="absolute top-3 left-3 md:top-4 md:left-4 text-gray-500 hover:text-white flex items-center gap-2 text-sm min-h-[44px] min-w-[44px] justify-center touch-manipulation">
          <ArrowLeft className="w-4 h-4" /> Back
        </button>

        <div className="text-center mb-6 md:mb-8 pt-8 md:pt-0">
          <h2 className="text-2xl md:text-3xl font-bold text-white mb-2">Forge Your Saga</h2>
          <div className="h-1 w-24 bg-purple-500 mx-auto rounded-full"></div>
        </div>

        {step === 1 && (
          <div className="space-y-5 md:space-y-6 animate-fade-in">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Story Title</label>
              <input 
                type="text" 
                placeholder="e.g., The Clockwork Crown" 
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-base text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none"
                value={data.title}
                onChange={e => setData({...data, title: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Genre</label>
              <select 
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-base text-white"
                value={data.genre}
                onChange={e => setData({...data, genre: e.target.value})}
              >
                <option>Fantasy</option>
                <option>Sci-Fi</option>
                <option>Cyberpunk</option>
                <option>Lovecraftian Horror</option>
                <option>Modern Slice of Life</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">The Premise</label>
              <textarea 
                placeholder="Describe the world and the initial conflict..." 
                rows="4"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-base text-white resize-none"
                value={data.premise}
                onChange={e => setData({...data, premise: e.target.value})}
              />
            </div>
            <button onClick={handleNext} disabled={!data.title} className="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold py-3.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed touch-manipulation active:scale-95">
              Next: Character Creation
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5 md:space-y-6 animate-fade-in">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Character Name</label>
              <input 
                type="text" 
                placeholder="Who are you playing?" 
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-base text-white"
                value={data.characterName}
                onChange={e => setData({...data, characterName: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Role / Class</label>
              <input 
                type="text" 
                placeholder="e.g. Exiled Paladin, Rogue Hacker" 
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-base text-white"
                value={data.characterRole}
                onChange={e => setData({...data, characterRole: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Character Background</label>
              <textarea 
                placeholder="What is their history, motivation, or dark secret?" 
                rows="4"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-base text-white resize-none"
                value={data.characterBackground}
                onChange={e => setData({...data, characterBackground: e.target.value})}
              />
            </div>
            
            <div className="flex gap-3 pt-2">
              <button onClick={handleBack} className="flex-1 bg-gray-800 hover:bg-gray-700 text-white font-bold py-3.5 rounded-lg touch-manipulation active:scale-95">
                Back
              </button>
              <button onClick={handleFinish} disabled={!data.characterName} className="flex-[2] bg-gradient-to-r from-purple-600 to-blue-600 hover:opacity-90 text-white font-bold py-3.5 rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 touch-manipulation active:scale-95">
                <Wand2 className="w-4 h-4 md:w-5 md:h-5" /> Begin Adventure
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
