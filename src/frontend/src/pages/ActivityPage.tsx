import { useEffect, useMemo, useState } from "react";
import type { components } from "../api/schema.d.ts";
import {
  ActorChip,
  aktorTipiSezgisi,
  EmptyState,
  HataDurumu,
  SonGuncelleme,
  YuklemeIskeleti,
} from "../components/ui";
import { useEvents } from "../lib/useEvents";

type NormalizedEvent = components["schemas"]["NormalizedEvent"];

/* Activity sayfası (#33 · #52 · #265 · #319) — "kendiliğinden daily".
   Kim dün ne yaptı, bugün neye başladı: GitHub olay akışının kişi ve gün
   bazında okunabilir hâli. Yazma YOK (CRUD yasağı, D-23) — bu bir okuma yüzü.

   Veri DB projeksiyonundan gelir (`EventRow`), GitHub portundan DEĞİL (#265):
   port `_seen_ids` ile "bu process'te görülmüş" olayları filtreler; ingest
   için doğru ama HTTP okuma için felaket — ikinci ziyaretçi boş feed alırdı.
   Ölçüldü: DB'li [3,3,3], DB'siz [3,0,0].

   #319 tasarım paritesi — üç madde ÇÖZÜLDÜ, ikisi ÖLÇÜLEREK stale bulundu:
   - Aktör türü filtresi (İnsan/Hepsi/Yalnız ajan) + görünüm anahtarı
     (Düz/Aktöre göre) + "↑ N yeni" rozeti: ÜÇÜ DE eldeki `events` listesinden
     istemci tarafında türetilir (aktör türü: `aktorTipiSezgisi`; "yeni":
     `ActivityPage` gövdesindeki `gorulenIdler` tabanına göre). Backend
     değişikliği GEREKMEDİ.
   - "Kendiliğinden Daily" kartı: Bugün/Dün satırları GERÇEK (aynı `events`'ten
     aktör+tür sayımı) — ama "blocker" satırı BİLİNÇLİ GATE'Lİ: ne
     `NormalizedEvent` ne `PresenceEntry` "blocker/engelleyici" alanı taşıyor
     (ölçüldü, 2026-07-29: `rg blocker` şemalarda sıfır sonuç) — GitHub
     commit/PR/issue olaylarından bu bilgi TÜRETİLEMEZ, uydurmak yerine
     satır tasarımdan eksik bırakıldı.
   - AŞAĞIDAKİ İKİ MADDE ESKİDEN "gate'li" sayılıyordu, ÖLÇÜLDÜĞÜNDE ikisi de
     ÇOKTAN ÇÖZÜLMÜŞ çıktı (bu yorum artık düzeltildi — yoksa yalan söylerdi):
     `/actors/:handle` kart detayına gidiş zaten ÇALIŞIYOR (`ActorChip
     linkli`, main.tsx route kayıtlı) · `since` cursor'ıyla artımlı yükleme
     zaten ÇALIŞIYOR (#273, bkz. `useEvents.ts` `imlec`). */

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

/** Bir aktör grubunun ÇİPİ doğrulanmış mı? (#296) — gruptaki HERHANGİ BİR
 * olay `actor_verified: false` taşıyorsa grup "eşleşmedi" sayılır (aynı
 * `actor` string'i normal şartlarda ya HEP login/username'den ya HEP ham
 * git adından gelir — ama tek bir kötü örnek bile varsa gizlenmemeli).
 * `actor_verified` alanı yoksa (eski/mock veri, additive+varsayılanlı model,
 * bkz. ensemble.models.NormalizedEvent) `undefined !== false` → doğrulanmış
 * sayılır, ActorChip'in kendi varsayılanıyla AYNI ilke.
 */
function grupDogrulanmisMi(olaylar: NormalizedEvent[]): boolean {
  return !olaylar.some((e) => e.actor_verified === false);
}

/** En yeni önce sıralar — TEK kaynak (grupla + gunlereBolFlat AYNI sırayı
    kullanır, ikisi ayrı ayrı sort yazsaydı iki farklı kayma riski dönerdi).
    Sıralama epoch üzerinden: string karşılaştırması naive/aware karışımında
    (biri 'Z'li, biri değil) sessizce yanlış sıralar. */
function sirali(events: NormalizedEvent[]): NormalizedEvent[] {
  return [...events].sort((a, b) => parseUtc(b.ts).getTime() - parseUtc(a.ts).getTime());
}

/** Olayları güne, gün içinde aktöre göre grupla — "Aktöre göre" görünümü. */
function grupla(events: NormalizedEvent[]) {
  const gunler = new Map<string, Map<string, NormalizedEvent[]>>();
  for (const e of sirali(events)) {
    const g = gunBasligi(e.ts);
    if (!gunler.has(g)) gunler.set(g, new Map());
    const aktorler = gunler.get(g)!;
    if (!aktorler.has(e.actor)) aktorler.set(e.actor, []);
    aktorler.get(e.actor)!.push(e);
  }
  return gunler;
}

/** Olayları güne böl, gün İÇİNDE aktöre göre ALT-GRUPLAMADAN — "Düz" görünümü
    (#319: tasarımda gün ayraçlı düz akış, aktör satırın kendisinde görünür). */
function gunlereBolFlat(events: NormalizedEvent[]): Map<string, NormalizedEvent[]> {
  const gunler = new Map<string, NormalizedEvent[]>();
  for (const e of sirali(events)) {
    const g = gunBasligi(e.ts);
    if (!gunler.has(g)) gunler.set(g, []);
    gunler.get(g)!.push(e);
  }
  return gunler;
}

/** Bir olay listesini aktör+tür bazında tek satırlık özetlere indirger —
    "Kendiliğinden Daily" kartının Bugün/Dün satırları (#319). GERÇEK sayım:
    aynı `events` üzerinden, uydurma yok. */
function aktorRollupSatirlari(olaylar: NormalizedEvent[]): string[] {
  const aktorBazinda = new Map<string, NormalizedEvent[]>();
  for (const e of olaylar) {
    if (!aktorBazinda.has(e.actor)) aktorBazinda.set(e.actor, []);
    aktorBazinda.get(e.actor)!.push(e);
  }
  return [...aktorBazinda.entries()].map(([aktor, liste]) => {
    const sayac = new Map<string, number>();
    for (const e of liste) sayac.set(e.type, (sayac.get(e.type) ?? 0) + 1);
    const ozet = [...sayac.entries()]
      .map(([tur, adet]) => `${adet} ${TUR[tur]?.etiket ?? tur}`)
      .join(" · ");
    return `${aktor}: ${ozet}`;
  });
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

/** "Düz" görünümün satırı — `OlaySatiri`'den TEK farkı: aktör çipi burada
    (grup başlığı yok, her satır kendi başına). `verified` grup-bazlı
    `grupDogrulanmisMi` yerine BU olayın kendi `actor_verified`'ı — düz
    görünümde grup kavramı yok, satır-başına dürüstlük daha isabetli. */
function DuzOlaySatiri({ e }: { e: NormalizedEvent }) {
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
      <ActorChip handle={e.actor} linkli verified={e.actor_verified !== false} />
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

const AKTOR_FILTRELERI = [
  { key: "human", label: "İnsan" },
  { key: "hepsi", label: "Hepsi" },
  { key: "agent", label: "Yalnız ajan" },
] as const;
type AktorFiltre = (typeof AKTOR_FILTRELERI)[number]["key"];

const GORUNUM_SECENEKLERI = [
  { key: "duz", label: "Düz" },
  { key: "gruplu", label: "Aktöre göre" },
] as const;
type Gorunum = (typeof GORUNUM_SECENEKLERI)[number]["key"];

/** "Kendiliğinden Daily — bugün" kartı (#319). Bugün/Dün satırları GERÇEK
    (aynı `events`'ten aktör+tür sayımı, bkz. `aktorRollupSatirlari`);
    blocker satırı BİLİNÇLİ YOK (dosya başındaki #319 notuna bkz.). */
function KendiliginDailyKarti({
  bugun,
  dun,
}: {
  bugun: NormalizedEvent[];
  dun: NormalizedEvent[];
}) {
  const [kopyalandi, setKopyalandi] = useState(false);
  const bugunSatirlari = aktorRollupSatirlari(bugun);
  const dunSatirlari = aktorRollupSatirlari(dun);

  async function kopyala() {
    const metin = [
      "Kendiliğinden Daily — bugün",
      "",
      "Bugün:",
      ...(bugunSatirlari.length > 0 ? bugunSatirlari.map((s) => `- ${s}`) : ["- henüz olay yok"]),
      "",
      "Dün:",
      ...(dunSatirlari.length > 0 ? dunSatirlari.map((s) => `- ${s}`) : ["- olay yok"]),
    ].join("\n");
    try {
      await navigator.clipboard.writeText(metin);
      setKopyalandi(true);
      setTimeout(() => setKopyalandi(false), 2000);
    } catch {
      /* clipboard izinsiz/desteksiz olabilir (http/eski tarayıcı) — best-effort,
         sayfa çalışmaya devam eder (GraphPage localStorage try/catch ilkesiyle aynı). */
    }
  }

  return (
    <div data-testid="daily-karti" className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Kendiliğinden Daily — bugün</h2>
        <button
          type="button"
          onClick={kopyala}
          className="shrink-0 rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted/50"
        >
          {kopyalandi ? "Kopyalandı ✓" : "Panoya kopyala"}
        </button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <h3 className="text-[11px] font-medium text-muted-foreground">Bugün</h3>
          {bugunSatirlari.length === 0 ? (
            <p className="text-xs text-muted-foreground">henüz olay yok</p>
          ) : (
            <ul className="space-y-0.5 text-xs">
              {bugunSatirlari.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="space-y-1">
          <h3 className="text-[11px] font-medium text-muted-foreground">Dün</h3>
          {dunSatirlari.length === 0 ? (
            <p className="text-xs text-muted-foreground">olay yok</p>
          ) : (
            <ul className="space-y-0.5 text-xs">
              {dunSatirlari.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ActivityPage() {
  const { data, error, isLoading, isFetching, dataUpdatedAt } = useEvents();

  const events = useMemo<NormalizedEvent[]>(() => data?.events ?? [], [data]);
  const [aktorFiltre, setAktorFiltre] = useState<AktorFiltre>("hepsi");
  const [gorunum, setGorunum] = useState<Gorunum>("gruplu");

  // "↑ N yeni" rozeti (#319): TAMAMEN istemci tarafı — ilk veri gelince
  // GÖRÜLEN id kümesi dondurulur (taban); sonraki poll'lerde tabanda
  // OLMAYAN id'ler "yeni" sayılır. Rozete tıklamak (`yeniGor`) tabanı ana
  // listeye eşitler (hepsini "görüldü" işaretler). Filtreden BAĞIMSIZ:
  // aktör filtresini değiştirmek yeni-sayısını DEĞİŞTİRMEZ (akışa GERÇEKTEN
  // yeni giren olay sayısını yansıtır, görünüme göre kaymaz).
  const [gorulenIdler, setGorulenIdler] = useState<Set<string> | null>(null);
  useEffect(() => {
    if (gorulenIdler === null && events.length > 0) {
      setGorulenIdler(new Set(events.map((e) => e.id)));
    }
  }, [gorulenIdler, events]);
  const yeniSayisi = gorulenIdler
    ? events.filter((e) => !gorulenIdler.has(e.id)).length
    : 0;
  const yeniGor = () => setGorulenIdler(new Set(events.map((e) => e.id)));

  const filtrelenmis = useMemo(
    () =>
      aktorFiltre === "hepsi"
        ? events
        : events.filter((e) => aktorTipiSezgisi(e.actor) === aktorFiltre),
    [events, aktorFiltre],
  );
  const gunler = useMemo(() => grupla(filtrelenmis), [filtrelenmis]);
  const gunlerFlat = useMemo(() => gunlereBolFlat(filtrelenmis), [filtrelenmis]);

  // Daily kartı BİLEREK filtreden bağımsız (tam tablo) — "bugün ne oldu"
  // sorusuna aktör-türü filtrelenmiş yarım cevap vermek yanıltıcı olurdu.
  const bugunOlaylari = useMemo(
    () => events.filter((e) => gunBasligi(e.ts) === "Bugün"),
    [events],
  );
  const dunOlaylari = useMemo(
    () => events.filter((e) => gunBasligi(e.ts) === "Dün"),
    [events],
  );

  if (isLoading) return <YuklemeIskeleti label="Olay akışı yükleniyor" satir={5} />;

  // `error != null`: openapi-fetch boş gövdeli non-ok yanıtta error olarak ""
  // (falsy) verebilir — `if (error)` yazılsaydı hata SESSİZCE yutulurdu.
  // Veri varken geçici poll hatası listeyi gizlemez (polling sürüyor).
  if (error != null && data === undefined)
    return <HataDurumu baslik="Olay akışına ulaşılamıyor" hata={error} />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-base font-semibold">Olay Akışı</h1>
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
          <KendiliginDailyKarti bugun={bugunOlaylari} dun={dunOlaylari} />

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex gap-1" role="group" aria-label="Aktör filtresi">
              {AKTOR_FILTRELERI.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setAktorFiltre(f.key)}
                  aria-pressed={aktorFiltre === f.key}
                  className={`rounded px-2 py-1 text-xs ${
                    aktorFiltre === f.key
                      ? "bg-muted font-medium"
                      : "text-muted-foreground hover:bg-muted/50"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="flex gap-1" role="group" aria-label="Görünüm">
              {GORUNUM_SECENEKLERI.map((g) => (
                <button
                  key={g.key}
                  type="button"
                  onClick={() => setGorunum(g.key)}
                  aria-pressed={gorunum === g.key}
                  className={`rounded px-2 py-1 text-xs ${
                    gorunum === g.key
                      ? "bg-muted font-medium"
                      : "text-muted-foreground hover:bg-muted/50"
                  }`}
                >
                  {g.label}
                </button>
              ))}
            </div>
            {yeniSayisi > 0 && (
              <button
                type="button"
                onClick={yeniGor}
                title="Görüldü işaretle"
                className="ml-auto rounded-full border border-primary/40 bg-primary/10 px-2 py-1 text-xs font-medium text-primary"
              >
                <span aria-hidden>↑</span> <span className="tabular-nums">{yeniSayisi}</span> yeni
              </button>
            )}
          </div>

          {filtrelenmis.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Bu filtrede olay yok — {events.length} olay diğer aktör türünde.
            </p>
          ) : gorunum === "duz" ? (
            [...gunlerFlat.entries()].map(([gun, olaylar]) => (
              <section key={gun} className="space-y-2">
                <h2 className="text-xs font-medium text-muted-foreground">
                  {gun}
                  <span className="ml-2 tabular-nums">{olaylar.length} olay</span>
                </h2>
                <ul
                  aria-label={`${gun} olayları (düz)`}
                  className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card"
                >
                  {olaylar.map((e) => (
                    <DuzOlaySatiri key={e.id} e={e} />
                  ))}
                </ul>
              </section>
            ))
          ) : (
            [...gunler.entries()].map(([gun, aktorler]) => (
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
                          İÇİNDE değil, satır kendi başına tıklanabilir değil.
                          verified (#296): bu gruptaki herhangi bir olay GitHub
                          hesabıyla eşleşmediyse çip bunu görünür kılar. */}
                      <ActorChip handle={aktor} linkli verified={grupDogrulanmisMi(olaylar)} />
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
            ))
          )}
        </div>
      )}
    </div>
  );
}
