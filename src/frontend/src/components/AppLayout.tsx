import { NavLink, Outlet } from "react-router-dom";
import { config } from "../lib/config";

/* Ters-L kabuk (Linear deseni): sol dar sidebar + üst ince bar.
   Sıra = demo anlatım sırası; Radar her zaman açılış sayfası. */

const NAV = [
  { to: "/", label: "Radar" },
  { to: "/board", label: "Board" },
  { to: "/scope", label: "Scope" },
  { to: "/graph", label: "Graf" },
  { to: "/activity", label: "Activity" },
  { to: "/ask", label: "Ask" },
];

export default function AppLayout() {
  return (
    <div className="flex h-screen">
      <aside className="flex w-44 flex-col border-r border-border">
        <div className="flex items-center gap-2 px-4 py-4">
          {/* Kesişim logosu placeholder'ı — Pencil'dan gelecek (D-34) */}
          <span className="inline-block size-3 rounded-full bg-primary" aria-hidden />
          <span className="text-sm font-semibold tracking-tight">Ensemble</span>
        </div>
        <nav className="flex-1 space-y-0.5 px-2">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                `block rounded px-2 py-1.5 text-sm ${
                  isActive
                    ? "bg-muted font-medium"
                    : "text-muted-foreground hover:bg-muted/50"
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-4 py-2">
          <span className="text-sm text-muted-foreground">grup54/ensemble</span>
          <div className="flex items-center gap-3">
            {config.mock && (
              // Sahte-canlılık yasak (D-34): mock modunda TÜM veriler örnektir —
              // tek şeride değil, globale işaret (yarım dürüstlük = dürüstsüzlük)
              <span className="rounded border border-status-in-review/40 bg-status-in-review/10 px-1.5 py-0.5 text-xs font-medium text-status-in-review">
                Örnek veri
              </span>
            )}
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
              {config.mode}
            </span>
            {/* health noktası — #20 canlandıracak (GET /health) */}
            <span
              className="size-2 rounded-full bg-status-backlog"
              title="Backend bağlantısı bekleniyor (#20)"
            />
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
