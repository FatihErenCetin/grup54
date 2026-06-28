"use client";

import { useState } from "react";

export default function Navbar() {
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  return (
    <nav
      id="top-navbar"
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-5 h-[52px]"
      style={{
        background: "rgba(11, 14, 20, 0.8)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {/* Left Section */}
      <div className="flex items-center gap-4">
        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{
              background:
                "linear-gradient(135deg, var(--accent-blue), var(--accent-cyan))",
            }}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <span
            className="text-sm font-semibold tracking-tight"
            style={{ color: "var(--text-primary)" }}
          >
            Harness
          </span>
        </div>

        {/* Divider */}
        <div
          className="w-px h-5"
          style={{ background: "var(--border-default)" }}
        />

        {/* Branch */}
        <div
          className="flex items-center gap-2 px-2.5 py-1 rounded-md text-xs"
          style={{
            background: "var(--accent-purple-dim)",
            color: "var(--accent-purple)",
          }}
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="6" y1="3" x2="6" y2="15" />
            <circle cx="18" cy="6" r="3" />
            <circle cx="6" cy="18" r="3" />
            <path d="M18 9a9 9 0 0 1-9 9" />
          </svg>
          <span className="font-mono font-medium">esma</span>
        </div>
      </div>

      {/* Center Section — Keyboard Shortcut Hint */}
      <div className="hidden md:flex items-center">
        <button
          id="cmd-k-trigger"
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-all duration-200"
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid var(--border-subtle)",
            color: "var(--text-muted)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(255,255,255,0.06)";
            e.currentTarget.style.borderColor = "var(--border-default)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "rgba(255,255,255,0.03)";
            e.currentTarget.style.borderColor = "var(--border-subtle)";
          }}
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <span>Search or ask...</span>
          <div className="flex items-center gap-1 ml-2">
            <kbd>⌘</kbd>
            <kbd>K</kbd>
          </div>
        </button>
      </div>

      {/* Right Section */}
      <div className="flex items-center gap-3.5">
        {/* System Status */}
        <div
          id="system-status"
          className="flex items-center gap-2 px-2.5 py-1 rounded-md text-xs"
          style={{
            background: "var(--accent-green-dim)",
            color: "var(--accent-green)",
          }}
        >
          <div className="status-dot animate-pulse-green" />
          <span className="font-medium hidden sm:inline">Healthy</span>
        </div>

        {/* Notifications */}
        <button
          id="notifications-btn"
          className="relative p-1.5 rounded-lg transition-colors duration-200"
          style={{ color: "var(--text-secondary)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(255,255,255,0.06)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
          }}
        >
          <svg
            width="17"
            height="17"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
          {/* Notification badge */}
          <span
            className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full"
            style={{
              background: "var(--accent-red)",
              border: "2px solid var(--bg-primary)",
            }}
          />
        </button>

        {/* User Avatar */}
        <div className="relative">
          <button
            id="user-profile-btn"
            className="flex items-center gap-2 p-1 pr-2 rounded-lg transition-all duration-200"
            onClick={() => setIsProfileOpen(!isProfileOpen)}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "rgba(255,255,255,0.06)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
            }}
          >
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold"
              style={{
                background:
                  "linear-gradient(135deg, var(--accent-purple), var(--accent-blue))",
                color: "white",
              }}
            >
              E
            </div>
            <span
              className="text-xs font-medium hidden sm:inline"
              style={{ color: "var(--text-secondary)" }}
            >
              esma
            </span>
            <svg
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              style={{ color: "var(--text-muted)" }}
              className="hidden sm:block"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          {/* Dropdown */}
          {isProfileOpen && (
            <div
              className="absolute right-0 top-10 w-48 rounded-xl py-1.5 animate-slide-up"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-default)",
                boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
              }}
            >
              <div
                className="px-3 py-2 text-xs border-b"
                style={{
                  color: "var(--text-muted)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                Signed in as <strong style={{ color: "var(--text-primary)" }}>esma</strong>
              </div>
              {["Settings", "API Keys", "Integrations"].map((item) => (
                <button
                  key={item}
                  className="w-full text-left px-3 py-2 text-xs transition-colors"
                  style={{ color: "var(--text-secondary)" }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = "var(--bg-hover)";
                    e.currentTarget.style.color = "var(--text-primary)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = "transparent";
                    e.currentTarget.style.color = "var(--text-secondary)";
                  }}
                >
                  {item}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
