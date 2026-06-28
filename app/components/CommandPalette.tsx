"use client";

import { useState, useEffect, useRef } from "react";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

const suggestions = [
  {
    icon: "🔍",
    text: "What did Cursor change in user-service?",
    tag: "Query",
    tagColor: "var(--accent-blue)",
  },
  {
    icon: "📊",
    text: "Show token usage for last 24h",
    tag: "Analytics",
    tagColor: "var(--accent-purple)",
  },
  {
    icon: "🔄",
    text: "Compare branch esma vs main",
    tag: "Diff",
    tagColor: "var(--accent-cyan)",
  },
  {
    icon: "⚠️",
    text: "List all unresolved conflicts",
    tag: "Conflicts",
    tagColor: "var(--accent-red)",
  },
  {
    icon: "📋",
    text: "Summarize today's AI activity",
    tag: "Summary",
    tagColor: "var(--accent-green)",
  },
  {
    icon: "🧠",
    text: "Explain the auth flow in this project",
    tag: "Context",
    tagColor: "var(--accent-yellow)",
  },
];

const recentCommands = [
  { icon: "↩️", text: "Rollback payment.ts to -30m", time: "5m ago" },
  { icon: "🔍", text: "What files did AI touch today?", time: "12m ago" },
  { icon: "📊", text: "Show conflict history", time: "1h ago" },
];

export default function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filteredSuggestions = query
    ? suggestions.filter(
        (s) =>
          s.text.toLowerCase().includes(query.toLowerCase()) ||
          s.tag.toLowerCase().includes(query.toLowerCase())
      )
    : suggestions;

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
    if (isOpen) {
      setQuery("");
      setSelectedIndex(0);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) =>
          prev < filteredSuggestions.length - 1 ? prev + 1 : 0
        );
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) =>
          prev > 0 ? prev - 1 : filteredSuggestions.length - 1
        );
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, filteredSuggestions.length]);

  if (!isOpen) return null;

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-[100]"
        style={{ background: "rgba(0, 0, 0, 0.5)", backdropFilter: "blur(4px)" }}
        onClick={onClose}
      />

      {/* Palette */}
      <div
        id="command-palette"
        className="fixed top-[18%] left-1/2 -translate-x-1/2 z-[101] w-full max-w-[620px] cmd-palette animate-slide-up"
      >
        {/* Input */}
        <div
          className="flex items-center gap-3 px-5 py-4"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--accent-cyan)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            placeholder="Ask the project brain (e.g., 'What did Cursor change in user-service?')"
            className="cmd-palette-input"
          />
          <div className="flex items-center gap-1 shrink-0">
            <kbd>esc</kbd>
          </div>
        </div>

        {/* Suggestions */}
        <div className="py-2 max-h-[340px] overflow-y-auto">
          {!query && (
            <div
              className="px-5 py-1.5 text-[10px] uppercase tracking-wider font-semibold"
              style={{ color: "var(--text-muted)" }}
            >
              Suggestions
            </div>
          )}
          {filteredSuggestions.map((item, index) => (
            <button
              key={index}
              className="w-full text-left flex items-center gap-3 px-5 py-2.5 transition-all duration-150"
              style={{
                background:
                  selectedIndex === index
                    ? "rgba(255,255,255,0.05)"
                    : "transparent",
                borderLeft:
                  selectedIndex === index
                    ? "2px solid var(--accent-cyan)"
                    : "2px solid transparent",
              }}
              onMouseEnter={() => setSelectedIndex(index)}
            >
              <span className="text-sm">{item.icon}</span>
              <span
                className="text-sm flex-1"
                style={{
                  color:
                    selectedIndex === index
                      ? "var(--text-primary)"
                      : "var(--text-secondary)",
                }}
              >
                {item.text}
              </span>
              <span
                className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                style={{
                  background: `${item.tagColor}18`,
                  color: item.tagColor,
                }}
              >
                {item.tag}
              </span>
            </button>
          ))}

          {query && filteredSuggestions.length === 0 && (
            <div
              className="px-5 py-8 text-center text-sm"
              style={{ color: "var(--text-muted)" }}
            >
              No results for &ldquo;{query}&rdquo;. Press Enter to ask the project brain.
            </div>
          )}

          {/* Recent */}
          {!query && (
            <>
              <div
                className="px-5 pt-3 pb-1.5 text-[10px] uppercase tracking-wider font-semibold"
                style={{
                  color: "var(--text-muted)",
                  borderTop: "1px solid rgba(255,255,255,0.04)",
                  marginTop: "4px",
                }}
              >
                Recent
              </div>
              {recentCommands.map((cmd, index) => (
                <button
                  key={`recent-${index}`}
                  className="w-full text-left flex items-center gap-3 px-5 py-2.5 transition-colors duration-150"
                  style={{ color: "var(--text-secondary)" }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = "rgba(255,255,255,0.04)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = "transparent";
                  }}
                >
                  <span className="text-sm">{cmd.icon}</span>
                  <span className="text-sm flex-1">{cmd.text}</span>
                  <span
                    className="text-[10px] font-mono"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {cmd.time}
                  </span>
                </button>
              ))}
            </>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-between px-5 py-2.5"
          style={{
            borderTop: "1px solid rgba(255,255,255,0.04)",
            color: "var(--text-muted)",
          }}
        >
          <div className="flex items-center gap-3 text-[10px]">
            <span className="flex items-center gap-1">
              <kbd>↑↓</kbd> navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd>↩</kbd> select
            </span>
            <span className="flex items-center gap-1">
              <kbd>esc</kbd> close
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-[10px]">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: "var(--accent-green)" }}
            />
            <span>Brain connected</span>
          </div>
        </div>
      </div>
    </>
  );
}
