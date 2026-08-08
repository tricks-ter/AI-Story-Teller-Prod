import React from 'react';

// Split narrative text into dialogue (in "quotes") vs narration segments.
export function splitNarrative(text) {
  const segments = [];
  const regex = /"([^"\n]*)"/g;
  let last = 0, m;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) segments.push({ type: 'narration', text: text.slice(last, m.index) });
    segments.push({ type: 'dialogue', text: m[0] });
    last = m.index + m[0].length;
  }
  if (last < text.length) segments.push({ type: 'narration', text: text.slice(last) });
  return segments;
}

export default function NarrativeBubble({ message, isStreaming }) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] bg-brand-600/20 border border-brand-500/30 rounded-2xl rounded-br-md px-4 py-3 text-gray-100 whitespace-pre-wrap leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  const segments = splitNarrative(message.content || '');

  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] bg-gray-800/60 border border-gray-700 rounded-2xl rounded-bl-md px-4 py-3 whitespace-pre-wrap leading-relaxed">
        {segments.map((s, i) =>
          s.type === 'dialogue'
            ? <span key={i} className="text-gray-100 font-medium not-italic">{s.text}</span>
            : <span key={i} className="text-gray-400 italic">{s.text}</span>
        )}
        {isStreaming && (
          <span className="ml-1 inline-block w-2 h-4 bg-brand-400 animate-pulse align-middle" />
        )}
      </div>
    </div>
  );
}
