"use client";

import { useState } from "react";

export default function AlertPanel() {
  const [conflictExpanded, setConflictExpanded] = useState(false);
  const [aiLoopExpanded, setAiLoopExpanded] = useState(false);

  return (
    <div
      id="alert-panel"
      className="fixed right-5 top-[68px] z-30 flex flex-col gap-4 w-[340px]"
    >
      {/* RED ZONE — Conflict Radar */}
      <div
        id="conflict-radar-card"
        className="glass-card-alert glass-red animate-float-in relative overflow-hidden"
        style={{ animationDelay: "0.1s", opacity: 0 }}
      >
        {/* Scanning overlay */}
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.03]"
          style={{
            background:
              "linear-gradient(180deg, transparent 0%, rgba(248, 81, 73, 0.3) 50%, transparent 100%)",
            animation: "scanning 4s ease-in-out infinite",
          }}
        />

        {/* Top accent bar */}
        <div
          className="absolute top-0 left-0 right-0 h-[2px]"
          style={{
            background:
              "linear-gradient(90deg, transparent, var(--accent-red), transparent)",
          }}
        />

        <div className="relative p-4">
          {/* Header */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div
                className="w-2.5 h-2.5 rounded-full animate-pulse-red"
                style={{ background: "var(--accent-red)" }}
              />
              <span
                className="text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--accent-red)" }}
              >
                Conflict Radar
              </span>
            </div>
            <button
              className="p-1 rounded-md transition-colors duration-200"
              style={{ color: "var(--text-muted)" }}
              onClick={() => setConflictExpanded(!conflictExpanded)}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(255,255,255,0.06)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
              }}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                style={{
                  transform: conflictExpanded ? "rotate(180deg)" : "rotate(0)",
                  transition: "transform 0.2s ease",
                }}
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
          </div>

          {/* Alert Text */}
          <p
            className="text-[13px] leading-relaxed mb-3"
            style={{ color: "var(--text-secondary)" }}
          >
            <span style={{ color: "var(--accent-red)" }}>⚠️ Alert:</span>{" "}
            Claude and Dev1 modifying the same module. Dry-run shows{" "}
            <strong
              className="font-mono"
              style={{ color: "var(--accent-red)" }}
            >
              85%
            </strong>{" "}
            merge conflict risk.
          </p>

          {/* Conflict risk bar */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1.5">
              <span
                className="text-[10px] font-medium"
                style={{ color: "var(--text-muted)" }}
              >
                Conflict Risk
              </span>
              <span
                className="text-[10px] font-mono font-bold"
                style={{ color: "var(--accent-red)" }}
              >
                85%
              </span>
            </div>
            <div
              className="h-1.5 rounded-full overflow-hidden"
              style={{ background: "rgba(248, 81, 73, 0.1)" }}
            >
              <div
                className="h-full rounded-full transition-all duration-1000 ease-out"
                style={{
                  width: "85%",
                  background:
                    "linear-gradient(90deg, var(--accent-yellow), var(--accent-red))",
                  boxShadow: "0 0 12px rgba(248, 81, 73, 0.3)",
                }}
              />
            </div>
          </div>

          {/* Affected files (expanded) */}
          {conflictExpanded && (
            <div
              className="mb-3 rounded-lg p-2.5 animate-slide-up"
              style={{
                background: "rgba(0,0,0,0.2)",
                border: "1px solid rgba(248, 81, 73, 0.1)",
              }}
            >
              <div
                className="text-[10px] font-semibold uppercase tracking-wider mb-2"
                style={{ color: "var(--text-muted)" }}
              >
                Affected Files
              </div>
              {[
                { file: "src/services/user-service.ts", lines: "L42-L89" },
                { file: "src/models/user.model.ts", lines: "L15-L28" },
                { file: "src/routes/auth.ts", lines: "L112-L130" },
              ].map((item, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-1"
                >
                  <span
                    className="text-[11px] font-mono"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {item.file}
                  </span>
                  <span
                    className="text-[10px] font-mono"
                    style={{ color: "var(--accent-red)" }}
                  >
                    {item.lines}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Actors */}
          <div className="flex items-center gap-2 mb-3">
            <div className="flex -space-x-1.5">
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold border-2"
                style={{
                  background:
                    "linear-gradient(135deg, var(--accent-purple), var(--accent-blue))",
                  borderColor: "var(--bg-primary)",
                  color: "white",
                }}
              >
                C
              </div>
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold border-2"
                style={{
                  background:
                    "linear-gradient(135deg, var(--accent-green), var(--accent-cyan))",
                  borderColor: "var(--bg-primary)",
                  color: "white",
                }}
              >
                D
              </div>
            </div>
            <span
              className="text-[10px] font-mono"
              style={{ color: "var(--text-muted)" }}
            >
              Claude · Dev1
            </span>
          </div>

          {/* Action */}
          <button id="review-diff-btn" className="btn-action btn-red w-full justify-center">
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
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
            Review Diff
          </button>
        </div>
      </div>

      {/* YELLOW ZONE — AI Cost Guard */}
      <div
        id="ai-cost-guard-card"
        className="glass-card-alert glass-yellow animate-float-in relative overflow-hidden"
        style={{ animationDelay: "0.3s", opacity: 0 }}
      >
        {/* Top accent bar */}
        <div
          className="absolute top-0 left-0 right-0 h-[2px]"
          style={{
            background:
              "linear-gradient(90deg, transparent, var(--accent-yellow), transparent)",
          }}
        />

        <div className="relative p-4">
          {/* Header */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div
                className="w-2.5 h-2.5 rounded-full animate-pulse-yellow"
                style={{ background: "var(--accent-yellow)" }}
              />
              <span
                className="text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--accent-yellow)" }}
              >
                Scope &amp; AI Cost Guard
              </span>
            </div>
            <button
              className="p-1 rounded-md transition-colors duration-200"
              style={{ color: "var(--text-muted)" }}
              onClick={() => setAiLoopExpanded(!aiLoopExpanded)}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(255,255,255,0.06)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
              }}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                style={{
                  transform: aiLoopExpanded ? "rotate(180deg)" : "rotate(0)",
                  transition: "transform 0.2s ease",
                }}
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
          </div>

          {/* Alert Text */}
          <p
            className="text-[13px] leading-relaxed mb-3"
            style={{ color: "var(--text-secondary)" }}
          >
            <span style={{ color: "var(--accent-yellow)" }}>⚠️ AI Loop:</span>{" "}
            Cursor iterating on{" "}
            <code
              className="px-1.5 py-0.5 rounded text-[11px] font-mono"
              style={{
                background: "rgba(210, 153, 34, 0.12)",
                color: "var(--accent-yellow)",
              }}
            >
              payment.ts
            </code>{" "}
            for{" "}
            <strong
              className="font-mono"
              style={{ color: "var(--accent-yellow)" }}
            >
              15+ mins
            </strong>
            . High token burn.
          </p>

          {/* Token Usage */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1.5">
              <span
                className="text-[10px] font-medium"
                style={{ color: "var(--text-muted)" }}
              >
                Token Consumption
              </span>
              <span
                className="text-[10px] font-mono font-bold"
                style={{ color: "var(--accent-yellow)" }}
              >
                12.4k / 15k limit
              </span>
            </div>
            <div
              className="h-1.5 rounded-full overflow-hidden"
              style={{ background: "rgba(210, 153, 34, 0.1)" }}
            >
              <div
                className="h-full rounded-full transition-all duration-1000 ease-out"
                style={{
                  width: "83%",
                  background:
                    "linear-gradient(90deg, var(--accent-green), var(--accent-yellow))",
                  boxShadow: "0 0 12px rgba(210, 153, 34, 0.2)",
                }}
              />
            </div>
          </div>

          {/* Expanded details */}
          {aiLoopExpanded && (
            <div
              className="mb-3 rounded-lg p-2.5 animate-slide-up"
              style={{
                background: "rgba(0,0,0,0.2)",
                border: "1px solid rgba(210, 153, 34, 0.1)",
              }}
            >
              <div
                className="text-[10px] font-semibold uppercase tracking-wider mb-2"
                style={{ color: "var(--text-muted)" }}
              >
                Loop Details
              </div>
              <div className="space-y-1.5">
                {[
                  { label: "Iterations", value: "23" },
                  { label: "Avg tokens/iter", value: "540" },
                  { label: "Duration", value: "15m 42s" },
                  { label: "Est. Cost", value: "$0.18" },
                ].map((item, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between"
                  >
                    <span
                      className="text-[11px]"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {item.label}
                    </span>
                    <span
                      className="text-[11px] font-mono font-medium"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {item.value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timer */}
          <div
            className="flex items-center gap-2 mb-3 px-2 py-1.5 rounded-md"
            style={{ background: "rgba(210, 153, 34, 0.06)" }}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--accent-yellow)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            <span
              className="text-[11px] font-mono"
              style={{ color: "var(--accent-yellow)" }}
            >
              Running: 15m 42s
            </span>
          </div>

          {/* Action */}
          <button id="pause-agent-btn" className="btn-action btn-yellow w-full justify-center">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="6" y="4" width="4" height="16" />
              <rect x="14" y="4" width="4" height="16" />
            </svg>
            Pause Agent
          </button>
        </div>
      </div>
    </div>
  );
}
