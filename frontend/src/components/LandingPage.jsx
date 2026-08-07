import React from 'react';
import { BookOpen, MessageSquare, Sparkles } from 'lucide-react';

export default function LandingPage({ onSelectChat, onSelectStory }) {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center justify-center p-6 relative overflow-hidden">
      {/* Background Glow Effects */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-purple-600/20 rounded-full blur-3xl animate-pulse"></div>
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-600/20 rounded-full blur-3xl animate-pulse delay-1000"></div>

      <div className="relative z-10 max-w-4xl w-full text-center space-y-8">
        {/* Hero Section */}
        <div className="flex items-center justify-center gap-3 mb-4">
          <div className="bg-gradient-to-tr from-purple-500 to-blue-500 p-3 rounded-2xl shadow-lg shadow-purple-500/20">
            <Sparkles className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-5xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400">
            InkMind
          </h1>
        </div>
        
        <p className="text-xl text-gray-400 max-w-2xl mx-auto leading-relaxed">
          The AI Narrative Engine. Whether you need a quick spark of inspiration or want to dive deep into an interactive world, we are ready to weave the story.
        </p>

        {/* The Two Portals */}
        <div className="grid md:grid-cols-2 gap-6 mt-12">
          
          {/* Portal 1: Quick Chat */}
          <button
            onClick={onSelectChat}
            className="group bg-gray-900/50 border border-gray-800 hover:border-blue-500/50 rounded-2xl p-8 text-left transition-all duration-300 hover:shadow-lg hover:shadow-blue-500/10 hover:-translate-y-1"
          >
            <div className="bg-blue-500/10 text-blue-400 p-3 rounded-xl w-fit mb-4 group-hover:scale-110 transition-transform">
              <MessageSquare className="w-6 h-6" />
            </div>
            <h3 className="text-2xl font-semibold mb-2 text-white">Quick Chat</h3>
            <p className="text-gray-400 text-sm leading-relaxed">
              Fast, unstructured brainstorming. Use this for coding help, quick questions, or general creative writing.
            </p>
            <div className="mt-4 text-sm text-blue-400 font-medium group-hover:underline">
              Launch Interface →
            </div>
          </button>

          {/* Portal 2: Story Engine */}
          <button
            onClick={onSelectStory}
            className="group bg-gray-900/50 border border-gray-800 hover:border-purple-500/50 rounded-2xl p-8 text-left transition-all duration-300 hover:shadow-lg hover:shadow-purple-500/10 hover:-translate-y-1 relative"
          >
            <div className="absolute top-4 right-4 bg-purple-500 text-white text-xs font-bold px-2 py-1 rounded-full">
              NEW
            </div>
            <div className="bg-purple-500/10 text-purple-400 p-3 rounded-xl w-fit mb-4 group-hover:scale-110 transition-transform">
              <BookOpen className="w-6 h-6" />
            </div>
            <h3 className="text-2xl font-semibold mb-2 text-white">Story Forge</h3>
            <p className="text-gray-400 text-sm leading-relaxed">
              Interactive Narrative RPG. Create a world, define your character, and let the AI Dungeon Master guide your adventure.
            </p>
            <div className="mt-4 text-sm text-purple-400 font-medium group-hover:underline">
              Create a Saga →
            </div>
          </button>
        </div>
        
        <p className="text-xs text-gray-600 mt-12">
          Powered by InkMind Nova & Pulse Models
        </p>
      </div>
    </div>
  );
}
