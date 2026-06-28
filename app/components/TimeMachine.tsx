"use client";

import { useState, useRef, useCallback } from "react";

const timeLabels = [
  { label: "−1h", position: 0 },
  { label: "−45m", position: 16.6 },
  { label: "−30m", position: 33.3 },
  { label: "−15m", position: 50 },
  { label: "−5m", position: 72 },
  { label: "Live", position: 100 },
];

const events = [
  { position: 8, type: "ai", label: "AI commit: auth refactor" },
  { position: 18, type: "system", label: "Docker restart" },
  { position: 28, type: "manual", label: "Manual push to main" },
  { position: 40, type: "ai", label: "Cursor: user-service edit" },
  { position: 55, type: "warning", label: "Type error detected" },
  { position: 65, type: "ai", label: "Claude: payment.ts fix" },
  { position: 78, type: "manual", label: "PR #47 merged" },
  { position: 88, type: "ai", label: "AI: route optimization" },
  { position: 95, type: "system", label: "Hot reload" },
];

export default function TimeMachine() {
  const [progress, setProgress] = useState(100);
  const [isPlaying, setIsPlaying] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [hoveredEvent, setHoveredEvent] = useState<number | null>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  const eventColor = (type: string) => {
    switch (type) {
      case "ai":
        return "var(--accent-blue)";
      case "manual":
        return "var(--accent-green)";
      case "system":
        return "var(--accent-purple)";
      case "warning":
        return "var(--accent-yellow)";
      default:
        return "var(--text-muted)";
    }
  };

  const handleTrackClick = useCallback(
    (e: React.MouseEvent) => {
      if (!trackRef.current) return;
      const rect = trackRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
      setProgress(pct);
    },
    []
  );

  const handleMouseDown = useCallback(() => {
    setIsDragging(true);

    const handleMouseMove = (e: MouseEvent) => {
      if (!trackRef.current) return;
      const rect = trackRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
      setProgress(pct);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  }, []);

  return (
    <div
      id="time-machine"
      className="fixed bottom-0 left-0 right-0 z-50 h-[56px] flex items-center px-5"
      style={{
        background: "rgba(11, 14, 20, 0.9)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderTop: "1px solid var(--border-subtle)",
      }}
    >
      {/* Play/Pause */}
      <button
        id="playback-toggle"
        onClick={() => setIsPlaying(!isPlaying)}
        className="mr-4 p-1.5 rounded-lg transition-all duration-200 shrink-0"
        style={{
          background: isPlaying
            ? "rgba(57, 208, 216, 0.1)"
            : "rgba(255,255,255,0.06)",
          color: isPlaying ? "var(--accent-cyan)" : "var(--text-secondary)",
          border: `1px solid ${
            isPlaying ? "rgba(57, 208, 216, 0.2)" : "var(--border-subtle)"
          }`,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = "scale(1.05)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = "scale(1)";
        }}
      >
        {isPlaying ? (
          <svg
            width="15"
            height="15"
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
        ) : (
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="currentColor"
          >
            <polygon points="6,3 20,12 6,21" />
          </svg>
        )}
      </button>

      {/* Time Label */}
      <div className="mr-4 shrink-0 w-[50px] text-right">
        <span
          className="text-[11px] font-mono font-bold"
          style={{
            color:
              progress >= 98 ? "var(--accent-cyan)" : "var(--text-secondary)",
          }}
        >
          {progress >= 98 ? "Live" : `−${Math.round((1 - progress / 100) * 60)}m`}
        </span>
      </div>

      {/* Timeline Track */}
      <div className="flex-1 relative" ref={trackRef}>
        {/* Clickable Area */}
        <div
          className="absolute inset-0 -top-3 -bottom-3 cursor-pointer z-10"
          onClick={handleTrackClick}
        />

        {/* Track Background */}
        <div className="timeline-track">
          {/* Progress */}
          <div
            className="timeline-progress"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Event Markers */}
        {events.map((event, index) => (
          <div
            key={index}
            className="absolute z-20"
            style={{
              left: `${event.position}%`,
              top: "50%",
              transform: "translate(-50%, -50%)",
            }}
            onMouseEnter={() => setHoveredEvent(index)}
            onMouseLeave={() => setHoveredEvent(null)}
          >
            <div
              className="w-2 h-2 rounded-full cursor-pointer transition-all duration-200"
              style={{
                background:
                  event.position <= progress
                    ? eventColor(event.type)
                    : "var(--text-muted)",
                boxShadow:
                  hoveredEvent === index
                    ? `0 0 10px ${eventColor(event.type)}`
                    : "none",
                transform:
                  hoveredEvent === index ? "scale(1.5)" : "scale(1)",
                opacity: event.position <= progress ? 1 : 0.3,
              }}
            />

            {/* Tooltip */}
            {hoveredEvent === index && (
              <div
                className="absolute bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap px-2.5 py-1.5 rounded-md text-[10px] font-medium animate-slide-up"
                style={{
                  background: "var(--bg-secondary)",
                  border: `1px solid ${eventColor(event.type)}30`,
                  color: "var(--text-primary)",
                  boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
                }}
              >
                <div className="flex items-center gap-1.5">
                  <div
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ background: eventColor(event.type) }}
                  />
                  {event.label}
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Draggable Thumb */}
        <div
          className="timeline-thumb"
          style={{ left: `${progress}%` }}
          onMouseDown={handleMouseDown}
        />

        {/* Time Labels */}
        <div className="absolute -bottom-5 left-0 right-0 flex justify-between pointer-events-none">
          {timeLabels.map((item) => (
            <span
              key={item.label}
              className="text-[9px] font-mono"
              style={{
                color: "var(--text-muted)",
                position: "absolute",
                left: `${item.position}%`,
                transform: "translateX(-50%)",
              }}
            >
              {item.label}
            </span>
          ))}
        </div>
      </div>

      {/* Context Hash */}
      <div className="ml-4 shrink-0 flex items-center gap-2">
        <div
          className="flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-mono"
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid var(--border-subtle)",
            color: "var(--text-muted)",
          }}
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          <span>.harness</span>
          <span style={{ color: "var(--accent-cyan)" }}>ctx:a3f7</span>
        </div>
      </div>
    </div>
  );
}
