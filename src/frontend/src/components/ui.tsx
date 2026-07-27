import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { AuthEylemSonucu } from "../lib/useAuth";

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

/* ── Yükleniyor / hata: TEK kalıp, tüm sayfalar (#20 hook'ları üç durumu da
   döndürür; sayfalar üçünü de çizmek ZORUNDA — hata yutmak yasak, D-34). ── */

export function YuklemeIskeleti({
  /** aria-label: "Board yükleniyor" gibi — ekran okuyucu ne beklediğini bilsin */
  label,
  satir = 3,
}: {
  label: string;
  satir?: number;
}) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label={label}>
      <div className="h-10 animate-pulse rounded-lg bg-muted" />
      {Array.from({ length: satir }, (_, i) => (
        <div key={i} className="h-14 animate-pulse rounded-lg bg-muted" />
      ))}
    </div>
  );
}

/** Hata gövdesini okunur tek satıra indirger — ErrorEnvelope {error,message,status},
    Error, düz string ve openapi-fetch'in boş-gövde ("") hâli dahil. */
export function hataMesaji(hata: unknown): string {
  if (hata === null || hata === undefined) return "";
  if (typeof hata === "string") return hata === "" ? "(boş hata gövdesi)" : hata;
  if (hata instanceof Error) return hata.message;
  if (typeof hata === "object") {
    const o = hata as { message?: unknown; detail?: unknown; error?: unknown };
    if (typeof o.message === "string" && o.message) return o.message;
    if (typeof o.detail === "string" && o.detail) return o.detail;
    if (typeof o.error === "string" && o.error) return o.error;
    try {
      return JSON.stringify(hata);
    } catch {
      return String(hata);
    }
  }
  return String(hata);
}

const BAGLANTI_ACIKLAMASI =
  "Backend cevap vermedi — bağlantıyı ve VITE_API_BASE_URL'i kontrol et. Polling sürüyor; düzelince kendiliğinden gelir.";

export function HataDurumu({
  /** "Board'a ulaşılamıyor" gibi — sayfa adını taşısın, "Bir hata oluştu" DEĞİL */
  baslik,
  aciklama = BAGLANTI_ACIKLAMASI,
  /** Ham hata: teknik ayrıntı satırı olarak GÖRÜNÜR basılır (yutulmaz) */
  hata,
}: {
  baslik: string;
  aciklama?: string;
  hata?: unknown;
}) {
  return (
    <div role="alert">
      <EmptyState title={baslik} description={aciklama} />
      {hata !== undefined && hata !== null && (
        <p className="mx-auto mt-3 max-w-md text-center font-mono text-[11px] text-muted-foreground">
          Teknik ayrıntı: {hataMesaji(hata)}
        </p>
      )}
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

/** RegisterPage + LoginPage'in ORTAK sonuç bloğu (T-294) — ikisi de aynı
    `AuthEylemSonucu` birleşimini aynı kurallarla çizer; iki yerde ayrı ayrı
    yazılsaydı biri güncellenip diğeri unutulabilirdi (drift). Yalnız
    `tur !== "basarili"` için çağrılır — başarıda sayfa zaten yönlendirir.
    429'da saniye biliniyorsa ("Retry-After" başlığı) TAM o cümle basılır
    (görev brifi: "N saniye sonra tekrar deneyin"); bilinmiyorsa backend'in
    kendi (uydurma olmayan) genel mesajına düşülür. */
export function AuthSonucMesaji({
  sonuc,
}: {
  sonuc: Exclude<AuthEylemSonucu, { tur: "basarili" }>;
}) {
  const mesaj =
    sonuc.tur === "cok_fazla_deneme" && sonuc.saniye !== null
      ? `${sonuc.saniye} saniye sonra tekrar deneyin.`
      : sonuc.mesaj;
  return (
    <p
      role="alert"
      className="rounded-lg border border-severity-high/40 bg-severity-high/10 px-3 py-2 text-xs text-severity-high"
    >
      {mesaj}
    </p>
  );
}

export function ConfidenceMeter({ value }: { value: number }) {
  // Judge güveni: mini-bar + sayı birlikte (renk/uzunluk tek başına anlam taşımaz — D-34)
  const pct = Math.round(value * 100);
  return (
    <span className="inline-flex items-center gap-1.5" title={`Judge güveni: %${pct}`}>
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-muted" aria-hidden>
        <span
          className="block h-full rounded-full bg-severity-med"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="text-xs tabular-nums text-muted-foreground">%{pct}</span>
    </span>
  );
}

const AGENT_SUFFIX = /-(claude|gemini|codex|kiro|bot|ai)$/i;

/** handle sonekinden insan/ajan SEZGİSİ — yalnız `ActorRef.type` yokken (#129).
    Tahmin ≠ veri: presence'tan gerçek tip gelirse HER ZAMAN onu tercih et. */
export function aktorTipiSezgisi(handle: string): "human" | "agent" {
  return AGENT_SUFFIX.test(handle) ? "agent" : "human";
}

export function ActorChip({
  handle,
  /** ActorRef.type — TAŞIYAN projeksiyonlarda (örn. PresenceEntry) verilir;
      verilmezse handle sonekinden sezilir (Detection.actors hâlâ düz string[]). */
  type,
  /** true ise `/actors/:handle` hub sayfasına link verir (#129 kabul kriteri:
      "Activity/Board/Radar'da handle tıklanabilir olsun"). Varsayılan false —
      görev kapsamı bu üç yüzeyle sınırlı (Graph/Presence/Login/AppLayout
      bilinçli DOKUNULMADI, "mevcut sayfaları minimum değiştir"). DİKKAT:
      `<a>` bir `<button>`/`<a>` İÇİNE giremez (geçersiz iç içe etkileşim) —
      true yalnız çip kendi başına duran bir konumdaysa güvenli (FeedItem'ın
      aktör satırı bilinçle butonun DIŞINA taşındı, bkz. FeedItem.tsx). */
  linkli = false,
}: {
  handle: string;
  type?: "human" | "agent";
  linkli?: boolean;
}) {
  // Tasarım dili: insan = daire, AI ajanı = kare (D-34). Kesin tip (Ek B1 ActorRef)
  // artık /presence'ta GELİYOR → varsa sezgiyi değil onu kullan (tahmin ≠ veri).
  const isAgent = type !== undefined ? type === "agent" : aktorTipiSezgisi(handle) === "agent";
  const initials = handle.slice(0, 2).toUpperCase();
  const icerik = (
    <>
      <span
        aria-hidden
        className={`inline-flex size-5 items-center justify-center bg-muted text-[10px] font-medium ${
          isAgent ? "rounded-sm" : "rounded-full"
        }`}
      >
        {initials}
      </span>
      <span className="text-xs text-muted-foreground">{handle}</span>
    </>
  );
  const baslik = isAgent ? `${handle} (AI ajanı)` : handle;
  if (linkli) {
    // title AYNEN korunur (linksiz varyantla): mevcut testler bu metni arıyor
    // (getByTitle) — link olmak tooltip'in ANLAMINI değiştirmez.
    return (
      <Link
        to={`/actors/${encodeURIComponent(handle)}`}
        title={baslik}
        className="inline-flex items-center gap-1 hover:underline"
      >
        {icerik}
      </Link>
    );
  }
  return (
    <span className="inline-flex items-center gap-1" title={baslik}>
      {icerik}
    </span>
  );
}
