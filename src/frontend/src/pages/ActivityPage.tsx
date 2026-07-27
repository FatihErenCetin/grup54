import { useMemo } from "react";
import type { components } from "../api/schema.d.ts";
import {
  ActorChip,
  EmptyState,
  HataDurumu,
  SonGuncelleme,
  YuklemeIskeleti,
} from "../components/ui";
import { useEvents } from "../lib/useEvents";

type NormalizedEvent = components["schemas"]["NormalizedEvent"];

/* Activity sayfası (#33 · #52 · #265) — "kendiliğinden daily".
   Kim dün ne yaptı, bugün neye başladı: GitHub olay akışının kişi ve gün
   bazında okunabilir hâli. Yazma YOK (CRUD yasağı, D-23) — bu bir okuma yüzü.

   Veri DB projeksiyonundan gelir (`EventRow`), GitHub portundan DEĞİL (#265):
   port `_seen_ids` ile "bu process'te görülmüş" olayları filtreler; ingest
   için doğru ama HTTP okuma için felaket — ikinci ziyaretçi boş feed alırdı.
   Ölçüldü: DB'li [3,3,3], DB'siz [3,0,0].

   Gate'li (bilinçli, eksik DEĞİL): aktör/tür filtresi · `since` cursor'ıyla
   artımlı yükleme (uç destekliyor, UI şimdilik tam feed okuyor) · kart
   detayına gidiş (/actors/:handle, S3-stretch). */

/** Backend naive-UTC ISO üretiyor (`"2026-07-27T22:30:00"` — zone eki YOK).
 * `new Date(iso)` bunu TARAYICI YEREL saati sanar: Europe/Istanbul'da
 * 27 Tem 22:30 hesaplanır, doğrusu 28 Tem 01:30'dur (3 saat kayma + yanlış
 * GÜN başlığı). Zone eki yoksa `Z` ekleyip UTC kabul ediyoruz.
 *
 * Gün başlığı, saat ve sıralama HEPSİ bu tek helper'dan geçer — üç yerde üç
 * farklı parse, üç farklı kayma demek olurdu.
 *
 * `export`: aynı `NormalizedEvent.ts` alanını render eden HER yüz bu parse'ı
 * kullanmalı — ActorPage (#129) ve ısı matrisi hücre listesi (#105) dahil.
 * İkinci bir kopya açılırsa iki farklı kayma riski geri gelir (ONU KULLAN). */
export function parseUtc(iso: string): Date {
  const zoneli = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
  return new Date(zoneli);
}

const TUR: Record<string, { etiket: string; ikon: string; ton: string }> = {
  commit: { etiket: "commit", ikon: "◆", ton: "bg-primary/15 text-primary" },
  pr: { etiket: "PR", ikon: "⇢", ton: "bg-status-in-review/15 text-status-in-review" },
  issue: { etiket: "issue", ikon: "◈", ton: "bg-status-todo/15 text-status-todo" },
};

function gunBasligi(iso: string): string {
  const d = parseUtc(iso);
  if (Number.isNaN(d.getTime())) return "Tarihi okunamayan olaylar";
  const bugun = new Date();
  const dun = new Date(bugun);
  dun.setDate(bugun.getDate() - 1);
  const ayniGun = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();
  if (ayniGun(d, bugun)) return "Bugün";
  if (ayniGun(d, dun)) return "Dün";
  return d.toLocaleDateString("tr-TR", { day: "numeric", month: "long", weekday: "long" });
}

function saat(iso: string): string {
  const d = parseUtc(iso);
  // Bozuk ISO'da ekrana "Invalid Date" basma (Scope/Graph ile aynı guard).
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

/** Olayları güne, gün içinde aktöre göre grupla — "kendiliğinden daily" şekli. */
function grupla(events: NormalizedEvent[]) {
  const gunler = new Map<string, Map<string, NormalizedEvent[]>>();
  // En yeni önce: feed'in doğal okuma sırası.
  // Sıralama da AYNI epoch üzerinden: string karşılaştırması naive/aware
  // karışımında (biri 'Z'li, biri değil) sessizce yanlış sıralar.
  const sirali = [...events].sort(
    (a, b) => parseUtc(b.ts).getTime() - parseUtc(a.ts).getTime(),
  );
  for (const e of sirali) {
    const g = gunBasligi(e.ts);
    if (!gunler.has(g)) gunler.set(g, new Map());
    const aktorler = gunler.get(g)!;
    if (!aktorler.has(e.actor)) aktorler.set(e.actor, []);
    aktorler.get(e.actor)!.push(e);
  }
  return gunler;
}

function OlaySatiri({ e }: { e: NormalizedEvent }) {
  const tur = TUR[e.type] ?? {
    etiket: e.type,
    ikon: "•",
    ton: "bg-muted text-muted-foreground",
  };
  const dosyaSayisi = e.files?.length ?? 0;
  return (
    <li className="flex items-start gap-2 px-4 py-2 text-sm hover:bg-muted/40">
      <span className="w-11 shrink-0 pt-0.5 text-[11px] tabular-nums text-muted-foreground">
        {saat(e.ts)}
      </span>
      <span className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] ${tur.ton}`}>
        <span aria-hidden="true">{tur.ikon}</span> {tur.etiket}
      </span>
      <span className="min-w-0 flex-1">
        {e.branch ? (
          <span className="font-mono text-xs text-muted-foreground">{e.branch}</span>
        ) : (
          <span className="text-xs text-muted-foreground">dalsız</span>
        )}
        {dosyaSayisi > 0 && (
          <>
            <span className="ml-2 text-[11px] tabular-nums text-muted-foreground">
              {dosyaSayisi} dosya
            </span>
            <span className="mt-0.5 block truncate font-mono text-[11px] text-muted-foreground/80">
              {e.files.slice(0, 3).join(" · ")}
              {dosyaSayisi > 3 ? ` +${dosyaSayisi - 3}` : ""}
            </span>
          </>
        )}
      </span>
    </li>
  );
}

export default function ActivityPage() {
  const { data, error, isLoading, isFetching, dataUpdatedAt } = useEvents();

  const events = useMemo<NormalizedEvent[]>(() => data?.events ?? [], [data]);
  const gunler = useMemo(() => grupla(events), [events]);

  if (isLoading) return <YuklemeIskeleti label="Olay akışı yükleniyor" satir={5} />;

  // `error != null`: openapi-fetch boş gövdeli non-ok yanıtta error olarak ""
  // (falsy) verebilir — `if (error)` yazılsaydı hata SESSİZCE yutulurdu.
  // Veri varken geçici poll hatası listeyi gizlemez (polling sürüyor).
  if (error != null && data === undefined)
    return <HataDurumu baslik="Olay akışına ulaşılamıyor" hata={error} />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-base font-semibold">Olay akışı</h1>
        <SonGuncelleme dataUpdatedAt={dataUpdatedAt} isFetching={isFetching} />
      </div>

      {events.length === 0 ? (
        <EmptyState
          title="Henüz olay yok"
          description="Bu akış GitHub'dan gelen commit, PR ve issue olaylarını kişi ve gün bazında toplar — 'kendiliğinden daily'. Webhook bağlıysa ilk olay geldiğinde burası kendiliğinden dolar."
          items={[
            "Veri kaynağı: ingest'in yazdığı DB projeksiyonu",
            "Yazma yok — bu bir okuma yüzü (D-23)",
          ]}
        />
      ) : (
        <div className="space-y-4">
          {[...gunler.entries()].map(([gun, aktorler]) => (
            <section key={gun} className="space-y-2">
              <h2 className="text-xs font-medium text-muted-foreground">
                {gun}
                <span className="ml-2 tabular-nums">
                  {[...aktorler.values()].reduce((t, l) => t + l.length, 0)} olay
                </span>
              </h2>
              {[...aktorler.entries()].map(([aktor, olaylar]) => (
                <div
                  key={aktor}
                  className="overflow-hidden rounded-lg border border-border bg-card"
                >
                  <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
                    {/* linkli: aktör hub'ına git (#129) — bu çip bir button/li
                        İÇİNDE değil, satır kendi başına tıklanabilir değil. */}
                    <ActorChip handle={aktor} linkli />
                    <span className="text-[11px] tabular-nums text-muted-foreground">
                      {olaylar.length} olay
                    </span>
                  </div>
                  <ul aria-label={`${aktor} olayları`} className="divide-y divide-border">
                    {olaylar.map((e) => (
                      <OlaySatiri key={e.id} e={e} />
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
