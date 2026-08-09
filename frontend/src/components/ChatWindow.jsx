import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import NarrativeBubble from "./NarrativeBubble";
import TypingIndicator from "./TypingIndicator";
import EmptyState from "./EmptyState";

export default function ChatWindow({
  messages,
  streamingMsg,
  isStreaming,
  statusText,
  onSuggestion,
  isStory,
}) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMsg, statusText]);

  const hasMessages = messages.length > 0 || streamingMsg;

  const renderBubble = (msg, streaming) =>
    msg.narrative ? (
      <NarrativeBubble key={msg.id} message={msg} isStreaming={streaming} />
    ) : (
      <MessageBubble key={msg.id} message={msg} isStreaming={streaming} />
    );

  return (
    <div className="flex-1 overflow-y-auto overscroll-contain">
      {!hasMessages ? (
        isStory ? (
          <div className="max-w-3xl mx-auto px-4 py-12 text-center">
            <p className="text-sm text-gray-400 italic leading-relaxed">
              The page is blank. The world holds its breath, waiting for your first move.
            </p>
            <div className="flex flex-wrap justify-center gap-2 mt-5">
              {["Look around carefully", "Move forward"].map(s => (
                <button
                  key={s}
                  onClick={() => onSuggestion(s)}
                  className="px-4 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 text-xs min-h-[44px] touch-manipulation active:scale-95"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <EmptyState onSuggestion={onSuggestion} />
        )
      ) : (
        <div className="max-w-3xl mx-auto px-3 sm:px-4 py-4 sm:py-6 space-y-6 sm:space-y-8">
          {messages.map((msg) => renderBubble(msg, false))}

          {streamingMsg && renderBubble(streamingMsg, isStreaming)}

          {isStreaming && !streamingMsg && (
            <TypingIndicator statusText={statusText} />
          )}

          <div ref={bottomRef} className="h-1" />
        </div>
      )}
    </div>
  );
}
