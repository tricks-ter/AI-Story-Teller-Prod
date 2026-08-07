import { useRef, useEffect } from "react";
import { Send, Square, Brain, Settings2 } from "lucide-react";
import { modelName } from "../utils/models";

export default function ChatInput({
  value, onChange, onSend, onStop, onOpenSettings, onToggleThinking,
  isStreaming, disabled, settings,
}) {
  const textareaRef = useRef(null);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 180) + "px";
  }, [value]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isStreaming && value.trim()) onSend();
    }
  };

  const modelShort = modelName(settings?.model);

  return (
    <div className="px-3 pb-3 pt-2 sm:px-4 sm:pb-4">
      <div className="flex items-center gap-2 mb-2 px-1">
        <button
          onClick={onOpenSettings}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-xs text-gray-400 hover:text-white transition-colors min-h-[36px] touch-manipulation"
        >
          <Settings2 size={12} />
          <span className="font-medium">{modelShort}</span>
        </button>

        <button
          onClick={onToggleThinking}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors min-h-[36px] touch-manipulation ${
            settings?.enableThinking
              ? "bg-brand-500/20 text-brand-300 hover:bg-brand-500/30"
              : "bg-gray-800 text-gray-500 hover:bg-gray-700 hover:text-gray-300"
          }`}
          title={settings?.enableThinking ? "Reasoning ON — click to disable" : "Reasoning OFF — click to enable"}
        >
          <Brain size={12} />
          <span className="hidden sm:inline">
            {settings?.enableThinking ? "Reasoning ON" : "Reasoning OFF"}
          </span>
          <span className="sm:hidden">
            {settings?.enableThinking ? "ON" : "OFF"}
          </span>
        </button>
      </div>

      <div className="flex items-end gap-2 bg-gray-800 border border-gray-700 rounded-2xl px-4 py-3 focus-within:border-brand-500 transition-colors duration-200">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message InkMind… (Shift+Enter for new line)"
          rows={1}
          disabled={disabled}
          className="flex-1 bg-transparent text-gray-100 placeholder-gray-500 resize-none outline-none leading-relaxed max-h-44 overflow-y-auto touch-manipulation"
          style={{ fontSize: "16px" }}
        />
        {isStreaming ? (
          <button
            onClick={onStop}
            className="flex-shrink-0 w-10 h-10 rounded-xl bg-red-500/20 hover:bg-red-500/40 text-red-400 hover:text-red-300 flex items-center justify-center transition-colors touch-manipulation"
            title="Stop generation"
          >
            <Square size={16} />
          </button>
        ) : (
          <button
            onClick={onSend}
            disabled={!value.trim() || disabled}
            className="flex-shrink-0 w-10 h-10 rounded-xl bg-brand-600 hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed text-white flex items-center justify-center transition-colors touch-manipulation"
            title="Send (Enter)"
          >
            <Send size={16} />
          </button>
        )}
      </div>

      <p className="text-xs text-gray-600 text-center mt-2">
        InkMind may make mistakes — verify important information.
      </p>
    </div>
  );
}
