import React from "react";
import { PlusCircle, MessageSquare, Trash2, Bot } from "lucide-react";
import HUD from "./HUD";

function formatDate(iso) {
  const d = new Date(iso);
  const diff = Date.now() - d;
  const m = Math.floor(diff / 60000);
  const h = Math.floor(diff / 3600000);
  const dy = Math.floor(diff / 86400000);
  if (m < 1) return "Just now";
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  if (dy < 7) return `${dy}d ago`;
  return d.toLocaleDateString();
}

export default function Sidebar({ sessions, activeId, onSelect, onCreate, onDelete, isOpen, storyContext }) {
  return (
    <aside
      className={`
        flex flex-col bg-gray-950 border-r border-gray-800
        w-72 flex-shrink-0
        fixed inset-y-0 left-0 z-30 transition-transform duration-300
        md:relative md:translate-x-0
        ${isOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full"}
      `}
    >
      {storyContext && <HUD storyContext={storyContext} />}
      
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-5 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-brand-600">
          <Bot size={18} className="text-white" />
        </div>
        <span className="text-white font-semibold text-lg tracking-tight">InkMind Chat</span>
      </div>

      {/* New Chat */}
      <div className="px-3 py-3 flex-shrink-0">
        <button
          onClick={onCreate}
          className="flex items-center gap-2 w-full px-4 py-3 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium transition-colors min-h-[48px] touch-manipulation"
        >
          <PlusCircle size={16} />
          New Chat
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-3 py-1 space-y-1">
        {sessions.length === 0 && (
          <p className="text-gray-500 text-xs text-center mt-8 px-4">
            No chats yet — start one!
          </p>
        )}
        {sessions.map((s) => (
          <div
            key={s.session_id}
            onClick={() => onSelect(s.session_id)}
            className={`
              group flex items-start gap-2 px-3 py-3 rounded-xl cursor-pointer
              transition-colors duration-150 min-h-[56px]
              ${
                activeId === s.session_id
                  ? "bg-brand-600/20 border border-brand-500/30"
                  : "hover:bg-gray-800 border border-transparent"
              }
            `}
          >
            <MessageSquare
              size={15}
              className={`mt-1 flex-shrink-0 ${
                activeId === s.session_id ? "text-brand-400" : "text-gray-500"
              }`}
            />
            <div className="flex-1 min-w-0">
              <p
                className={`text-sm truncate leading-snug ${
                  activeId === s.session_id ? "text-white font-medium" : "text-gray-300"
                }`}
              >
                {s.title || "New Chat"}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">
                {s.messages?.length ?? 0} msg{(s.messages?.length ?? 0) !== 1 ? "s" : ""}{" "}
                · {formatDate(s.created_at)}
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(s.session_id);
              }}
              className="opacity-0 group-hover:opacity-100 p-2 rounded-lg hover:bg-red-500/20 text-gray-500 hover:text-red-400 transition-all flex-shrink-0 touch-manipulation"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-800 flex-shrink-0">
        <p className="text-xs text-gray-600 text-center">Z.AI · InkMind Models</p>
      </div>
    </aside>
  );
}
