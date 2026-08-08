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
}) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMsg, statusText]);

  const hasMessages = messages.length > 0 || streamingMsg;

  const renderBubble = (msg, streaming) =>
    msg.narrative ? (
      <NarrativeBubble message={msg} isStreaming={streaming} />
    ) : (
      <MessageBubble message={msg} isStreaming={streaming} />
    );

  return (
    <div className="flex-1 overflow-y-auto overscroll-contain">
      {!hasMessages ? (
        <EmptyState onSuggestion={onSuggestion} />
      ) : (
        <div className="max-w-3xl mx-auto px-3 sm:px-4 py-4 sm:py-6 space-y-6 sm:space-y-8">
          {messages.map((msg) => (
            <React.Fragment key={msg.id}>{renderBubble(msg, false)}</React.Fragment>
          ))}

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
