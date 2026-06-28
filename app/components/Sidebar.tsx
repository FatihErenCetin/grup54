"use client";

import { useState, useEffect } from "react";

interface ActivityItem {
  id: number;
  icon: string;
  text: string;
  time: string;
  type: "ai" | "manual" | "system" | "warning";
}

const initialActivities: ActivityItem[] = [
  {
    id: 1,
    icon: "🤖",
    text: "AI updated route /api/users",
    time: "2s ago",
    type: "ai",
  },
  {
    id: 2,
    icon: "✅",
    text: "Manual commit pushed to main",
    time: "1m ago",
    type: "manual",
  },
  {
    id: 3,
    icon: "🔄",
    text: "Cursor refactoring auth.ts",
    time: "2m ago",
    type: "ai",
  },
  {
    id: 4,
    icon: "📦",
    text: "npm install completed",
    time: "5m ago",
    type: "system",
  },
  {
    id: 5,
    icon: "⚠️",
    text: "Type error in payment.ts:42",
    time: "8m ago",
    type: "warning",
  },
  {
    id: 6,
    icon: "🤖",
    text: "Claude modified user-service",
    time: "10m ago",
    type: "ai",
  },
  {
    id: 7,
    icon: "✅",
    text: "Tests passing: 42/42",
    time: "12m ago",
    type: "manual",
  },
  {
    id: 8,
    icon: "🔄",
    text: "Hot reload triggered",
    time: "14m ago",
    type: "system",
  },
  {
    id: 9,
    icon: "🤖",
    text: "AI generated migration file",
    time: "18m ago",
    type: "ai",
  },
  {
    id: 10,
    icon: "📦",
    text: "Docker container restarted",
    time: "22m ago",
    type: "system",
  },
  {
    id: 11,
    icon: "✅",
    text: "PR #47 merged by esma",
    time: "25m ago",
    type: "manual",
  },
  {
    id: 12,
    icon: "🤖",
    text: "Copilot suggested fix for #128",
    time: "30m ago",
    type: "ai",
  },
];

const newActivities: ActivityItem[] = [
  {
    id: 100,
    icon: "🤖",
    text: "AI optimized DB query in orders.ts",
    time: "just now",
    type: "ai",
  },
  {
    id: 101,
    icon: "✅",
    text: "Lint check passed",
    time: "just now",
    type: "manual",
  },
  {
    id: 102,
    icon: "🔄",
    text: "Cursor editing middleware.ts",
    time: "just now",
    type: "ai",
  },
  {
    id: 103,
    icon: "📦",
    text: "New dependency installed: zod@3.22",
    time: "just now",
    type: "system",
  },
];

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

let idCounter = 1000;

export default function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const [activities, setActivities] = useState<ActivityItem[]>(initialActivities);
  const [newItemIndex, setNewItemIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setNewItemIndex((prev) => {
        const nextIndex = (prev + 1) % newActivities.length;
        idCounter += 1;
        const newItem = {
          ...newActivities[nextIndex],
          id: idCounter,
          time: "just now",
        };
        setActivities((prevActivities) => [newItem, ...prevActivities.slice(0, 14)]);
        return nextIndex;
      });
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const typeColor = (type: ActivityItem["type"]) => {
    switch (type) {
      case "ai":
        return "var(--accent-blue)";
      case "manual":
        return "var(--accent-green)";
      case "system":
        return "var(--accent-purple)";
      case "warning":
        return "var(--accent-yellow)";
    }
  };

  return (
    <aside
      id="activity-sidebar"
      className="fixed left-0 top-[52px] bottom-[56px] z-40 transition-all duration-300 ease-in-out flex flex-col"
      style={{
        width: isCollapsed ? "48px" : "272px",
        background: "rgba(11, 14, 20, 0.85)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderRight: "1px solid var(--border-subtle)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 h-10 shrink-0"
        style={{ borderBottom: "1px solid var(--border-subtle)" }}
      >
        {!isCollapsed && (
          <div className="flex items-center gap-2">
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: "var(--accent-green)" }}
            />
            <span
              className="text-[11px] font-semibold uppercase tracking-wider"
              style={{ color: "var(--text-muted)" }}
            >
              Activity Feed
            </span>
          </div>
        )}
        <button
          id="sidebar-toggle"
          onClick={onToggle}
          className="p-1 rounded-md transition-colors duration-200"
          style={{ color: "var(--text-muted)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(255,255,255,0.06)";
            e.currentTarget.style.color = "var(--text-secondary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "var(--text-muted)";
          }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            {isCollapsed ? (
              <>
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </>
            ) : (
              <>
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </>
            )}
          </svg>
        </button>
      </div>

      {/* Activity List */}
      {!isCollapsed && (
        <div className="flex-1 overflow-y-auto">
          {activities.map((activity, index) => (
            <div
              key={activity.id}
              className="feed-item animate-fade-in-slide"
              style={{
                animationDelay: `${index * 30}ms`,
                opacity: 0,
                animationFillMode: "forwards",
              }}
            >
              <div className="flex items-start gap-2.5">
                <span className="text-sm mt-0.5 shrink-0">{activity.icon}</span>
                <div className="min-w-0 flex-1">
                  <p
                    className="text-[12px] leading-[1.4] break-words"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {activity.text}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <div
                      className="w-1 h-1 rounded-full"
                      style={{ background: typeColor(activity.type) }}
                    />
                    <span
                      className="text-[10px] font-mono"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {activity.time}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Collapsed: Icon-only */}
      {isCollapsed && (
        <div className="flex-1 flex flex-col items-center pt-3 gap-2 overflow-hidden">
          {activities.slice(0, 8).map((activity) => (
            <div
              key={activity.id}
              className="w-7 h-7 rounded-md flex items-center justify-center text-sm cursor-default transition-all duration-200"
              title={activity.text}
              style={{ background: "rgba(255,255,255,0.03)" }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(255,255,255,0.08)";
                e.currentTarget.style.transform = "scale(1.1)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "rgba(255,255,255,0.03)";
                e.currentTarget.style.transform = "scale(1)";
              }}
            >
              {activity.icon}
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
