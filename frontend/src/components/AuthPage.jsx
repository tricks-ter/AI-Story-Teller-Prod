import React, { useState } from 'react';
import { ArrowLeft, LogIn, UserPlus } from 'lucide-react';
import { BASE_URL, saveAuth } from '../utils/auth';

export default function AuthPage({ onAuthed, onBack }) {
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await fetch(`${BASE_URL}/auth/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, remember_me: remember })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Authentication failed');
      saveAuth(data.token, data.user, remember);
      onAuthed(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-[100dvh] bg-gray-950 text-gray-100 flex flex-col items-center p-4">
      <div className="my-auto w-full max-w-md bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl p-6 md:p-8 relative my-6">
        <button onClick={onBack} className="absolute top-3 left-3 text-gray-500 hover:text-white flex items-center gap-2 text-sm min-h-[44px] min-w-[44px] justify-center touch-manipulation">
          <ArrowLeft className="w-4 h-4" /> Back
        </button>

        <div className="text-center mb-6 pt-6">
          <h2 className="text-2xl font-bold text-white">{mode === 'login' ? 'Welcome Back' : 'Create Account'}</h2>
          <p className="text-sm text-gray-500 mt-1">Sign in to continue your journey</p>
        </div>

        {error && (
          <div className="mb-4 px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={submit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">Username</label>
            <input
              type="text"
              autoComplete="username"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-base text-white focus:border-purple-500 outline-none"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">Password</label>
            <input
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-base text-white focus:border-purple-500 outline-none"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>

          {mode === 'login' && (
            <label className="flex items-center gap-3 text-sm text-gray-400 touch-manipulation min-h-[32px]">
              <input
                type="checkbox"
                checked={remember}
                onChange={e => setRemember(e.target.checked)}
                className="w-5 h-5 rounded bg-gray-800 border-gray-700 accent-purple-600"
              />
              Remember me on this device
            </label>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:opacity-90 text-white font-bold py-3.5 rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 touch-manipulation active:scale-95"
          >
            {mode === 'login' ? <LogIn className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
            {busy ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Sign Up'}
          </button>
        </form>

        <p className="text-center text-sm text-gray-500 mt-6">
          {mode === 'login' ? 'New to InkMind?' : 'Already have an account?'}{' '}
          <button
            onClick={() => { setMode(m => m === 'login' ? 'signup' : 'login'); setError(null); }}
            className="text-purple-400 font-medium hover:underline touch-manipulation"
          >
            {mode === 'login' ? 'Create an account' : 'Sign in'}
          </button>
        </p>
      </div>
    </div>
  );
}
