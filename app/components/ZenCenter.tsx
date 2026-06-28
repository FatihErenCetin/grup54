"use client";

export default function ZenCenter() {
  return (
    <div className="flex flex-col items-center justify-center h-full select-none">
      {/* Subtle glow background */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 600px 400px at 50% 45%, rgba(57, 208, 216, 0.03) 0%, transparent 70%)",
        }}
      />

      {/* Main prompt area */}
      <div className="relative z-10 flex flex-col items-center gap-6 max-w-lg">
        {/* Logo / Icon */}
        <div
          className="w-16 h-16 rounded-2xl flex items-center justify-center animate-glow-pulse"
          style={{
            background:
              "linear-gradient(135deg, rgba(88, 166, 255, 0.1), rgba(57, 208, 216, 0.1))",
            border: "1px solid rgba(57, 208, 216, 0.15)",
          }}
        >
          <svg
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--accent-cyan)"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
        </div>

        {/* Title */}
        <div className="text-center">
          <h1
            className="text-2xl font-semibold tracking-tight mb-2"
            style={{
              background:
                "linear-gradient(135deg, var(--text-primary) 0%, var(--text-secondary) 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            What would you like to know?
          </h1>
          <p
            className="text-sm"
            style={{ color: "var(--text-muted)" }}
          >
            Press{" "}
            <kbd className="mx-0.5">⌘</kbd>
            <kbd className="mx-0.5">K</kbd>{" "}
            to search or ask the project brain
          </p>
        </div>

        {/* Quick Actions */}
        <div className="flex flex-wrap items-center justify-center gap-2 mt-2">
          {[
            { icon: "🔍", label: "Search files", shortcut: "⌘P" },
            { icon: "🧠", label: "Ask AI", shortcut: "⌘K" },
            { icon: "📊", label: "View metrics", shortcut: "⌘M" },
            { icon: "⏪", label: "Replay events", shortcut: "⌘T" },
          ].map((action) => (
            <button
              key={action.label}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-all duration-200 group"
              style={{
                background: "rgba(255,255,255,0.02)",
                border: "1px solid var(--border-subtle)",
                color: "var(--text-muted)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(255,255,255,0.05)";
                e.currentTarget.style.borderColor = "var(--border-default)";
                e.currentTarget.style.color = "var(--text-secondary)";
                e.currentTarget.style.transform = "translateY(-1px)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "rgba(255,255,255,0.02)";
                e.currentTarget.style.borderColor = "var(--border-subtle)";
                e.currentTarget.style.color = "var(--text-muted)";
                e.currentTarget.style.transform = "translateY(0)";
              }}
            >
              <span>{action.icon}</span>
              <span>{action.label}</span>
              <kbd className="ml-1">{action.shortcut}</kbd>
            </button>
          ))}
        </div>

        {/* Stats row */}
        <div
          className="flex items-center gap-6 mt-4 px-5 py-3 rounded-xl"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          {[
            {
              label: "AI Actions",
              value: "142",
              color: "var(--accent-blue)",
            },
            {
              label: "Commits",
              value: "38",
              color: "var(--accent-green)",
            },
            {
              label: "Conflicts",
              value: "3",
              color: "var(--accent-red)",
            },
            {
              label: "Uptime",
              value: "99.2%",
              color: "var(--accent-cyan)",
            },
          ].map((stat, i) => (
            <div key={stat.label} className="flex flex-col items-center">
              {i > 0 && (
                <div
                  className="absolute -left-3 h-6 w-px"
                  style={{ background: "var(--border-subtle)" }}
                />
              )}
              <span
                className="text-lg font-semibold font-mono"
                style={{ color: stat.color }}
              >
                {stat.value}
              </span>
              <span
                className="text-[10px] mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {stat.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
