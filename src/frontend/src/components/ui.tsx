import type { ReactNode } from "react";

/* Çekirdek UI primitive'leri (#19) — shadcn/ui adlandırma/token uyumlu;
   S2 iskeleti için el yazımı, shadcn CLI onboarding'i #21 ile gelir. */

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-border bg-card p-4 ${className}`}>
      {children}
    </div>
  );
}

type Severity = "high" | "med" | "low";

const severityStyle: Record<Severity, { cls: string; label: string; icon: string }> = {
  // Renk + ikon + etiket birlikte (renk tek başına anlam taşımaz — D-34)
  high: { cls: "bg-severity-high/15 text-severity-high", label: "yüksek", icon: "▲" },
  med: { cls: "bg-severity-med/15 text-severity-med", label: "orta", icon: "◆" },
  low: { cls: "bg-severity-low/15 text-severity-low", label: "düşük", icon: "●" },
};

export function SeverityBadge({ level }: { level: Severity }) {
  const s = severityStyle[level];
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${s.cls}`}>
      <span aria-hidden>{s.icon}</span>
      {s.label}
    </span>
  );
}

export function EmptyState({
  title,
  description,
  items,
  eta,
}: {
  title: string;
  description: string;
  items?: string[];
  eta?: string;
}) {
  return (
    <div className="mx-auto mt-16 max-w-md text-center">
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{description}</p>
      {items && (
        <ul className="mt-4 space-y-1 text-left text-sm text-muted-foreground">
          {items.map((it) => (
            <li key={it} className="rounded border border-border bg-card px-3 py-2">
              {it}
            </li>
          ))}
        </ul>
      )}
      {eta && <p className="mt-4 text-xs text-muted-foreground">{eta}</p>}
    </div>
  );
}

export function SonGuncelleme({
  dataUpdatedAt,
  isFetching = false,
}: {
  /** usePolling'den gelen GERÇEK zaman (ms epoch); 0 = henüz veri yok */
  dataUpdatedAt: number;
  isFetching?: boolean;
}) {
  // Sahte-canlılık yasak (D-34): saat uydurulmaz, son BAŞARILI verinin zamanı
  // basılır. Sekme arka planda kaldıysa eski saat DÜRÜSTÇE görünür; odakta
  // usePolling anında tazeler (isFetching o geçişi görünür kılar).
  // ts UTC gelir, yerel saate çeviri istemcide (Ek B5).
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      {isFetching && (
        <span aria-hidden className="animate-pulse text-primary">
          ●
        </span>
      )}
      {dataUpdatedAt === 0
        ? "Henüz veri yok"
        : `Son güncelleme: ${new Date(dataUpdatedAt).toLocaleTimeString("tr-TR")}`}
    </span>
  );
}
