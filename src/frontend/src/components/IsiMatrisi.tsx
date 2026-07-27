import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { components } from "../api/schema.d.ts";
import { useEvents } from "../lib/useEvents";
import { useGraph } from "../lib/useGraph";
import { parseUtc } from "../pages/ActivityPage";
import { ActorChip, hataMesaji } from "./ui";

type GraphEdge = components["schemas"]["GraphEdge"];
type NormalizedEvent = components["schemas"]["NormalizedEvent"];

/* #105 — Radar'ın "neden" haritası: çakışma radarı "çakışma var" der, bu
   panel "çünkü X ve Y aynı modülde" gösterir. `GET /graph` (#104) zaten tam
   sayfalık bir ısı matrisi + pencere seçici sunuyor (`pages/GraphPage.tsx`);
   O SAYFA DEĞİŞTİRİLMİYOR — bu, Radar'a GÖMÜLÜ, ayrı ve daha küçük bir
   bileşen: pencere sabit (backend varsayılanı), amaç tek bakışta bağlam.
   Derinlemesine inceleme (pencere seçimi, kenar detay paneli) için "Graf"
   sayfasına link veriyoruz (ölü link DEĞİL — `/graph` gerçek bir route).

   Renk dili kararı (kabul kriteri: "Detection.actors ile tutarlı"): app'te
   aktöre özel bir renk/hue YOK — tutarlılık `ActorChip`'in KENDİSİ (insan =
   daire, AI ajanı = kare, hep `bg-muted`). `FeedItem`/`DetailSheet` de
   `Detection.actors`'ı aynı bileşenle çizer; burada YENİ bir aktör-renk
   şeması İCAT ETMİYORUZ, aynı çipi kullanıyoruz. Yoğunluk (ısı) rengi ayrı
   bir kanal: sayı her hücrede yazılı + title/aria (D-34, renk tek başına
   anlam taşımaz).

   Panel KENDİ katlanma durumunu tutar (varsayılan kapalı) — RadarPage'e tek
   satır `<IsiMatrisi />` ile eklenir, mevcut akış bozulmaz. Kapalıyken hiçbir
   istek atılmaz (gövde hiç mount olmaz) — kapalı panel için gereksiz polling
   yok. */

const ISI_SINIFLARI = [
  "bg-primary/10 text-foreground",
  "bg-primary/25 text-foreground",
  "bg-primary/45 text-foreground",
  "bg-primary/70 text-primary-foreground",
  "bg-primary text-primary-foreground",
] as const;

/** Hücrenin ısı sınıfı — en yoğun hücreye GÖRECELİ (GraphPage ile aynı ölçek
    mantığı). İndeks daima kenetlenir: bozuk/0 `count` className'e `undefined`
    sızdırmaz. */
function isiSinifi(count: number, enYogun: number): string {
  const oran = enYogun > 0 ? count / enYogun : 0;
  const k = Math.ceil(oran * ISI_SINIFLARI.length);
  const i = Math.min(ISI_SINIFLARI.length - 1, Math.max(0, k - 1));
  return ISI_SINIFLARI[i];
}

/** Backend `engine/graph.py::_module_of` ile BİREBİR AYNI kural (kontrat:
    modül path'ten hesaplanır, şemaya yazılmaz). İki taraf ayrı hesap yaparsa
    hücre tıklaması yanlış olayları eşlerdi — tek kaynaktan (backend) elle
    aynalanıyor, `src/shared/openapi.json` bu hesabı taşımıyor. */
function moduleOfPath(path: string): string {
  const parts = path.split("/").filter(Boolean);
  if (parts.length === 0) return "";
  if (parts[0] === "src" && parts.length > 1) return parts[1];
  return parts[0];
}

function eventModules(e: NormalizedEvent): Set<string> {
  return new Set(e.files.filter(Boolean).map(moduleOfPath));
}

const TUR: Record<string, { etiket: string; ikon: string }> = {
  commit: { etiket: "commit", ikon: "◆" },
  pr: { etiket: "PR", ikon: "⇢" },
  issue: { etiket: "issue", ikon: "◈" },
  branch: { etiket: "branch", ikon: "⑂" },
};

/** Bozuk ISO ekrana "Invalid Date" basmaz (Activity/Graph ile aynı guard). */
function tarihMetni(iso: string): string {
  const d = parseUtc(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("tr-TR");
}

type Secim = { actor: string; module: string };

export function IsiMatrisi() {
  const [acik, setAcik] = useState(false);
  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setAcik((a) => !a)}
        aria-expanded={acik}
        aria-controls="isi-matrisi-govde"
        className="flex w-full items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-left text-xs text-muted-foreground hover:bg-muted/40"
      >
        <span aria-hidden className="font-mono">
          {acik ? "▾" : "▸"}
        </span>
        <span className="font-medium text-foreground">Aktör × modül ısı matrisi</span>
        <span className="truncate">
          — {acik ? "gizlemek için tıkla" : "radar neden uyarıyor, hangi modülde görün"}
        </span>
      </button>
      {/* Kapalıyken mount OLMAZ: useGraph/useEvents burada, kapalı panel
          gereksiz istek atmaz (polling yalnız açıkken çalışır). */}
      {acik && (
        <div id="isi-matrisi-govde">
          <IsiMatrisiGovde />
        </div>
      )}
    </div>
  );
}

function IsiMatrisiGovde() {
  const { data, error, isLoading } = useGraph();
  const eventsQ = useEvents();
  const [secim, setSecim] = useState<Secim | null>(null);

  const veri = useMemo(() => {
    const edges: GraphEdge[] = data?.edges ?? [];
    const satirToplam = new Map<string, number>();
    const sutunToplam = new Map<string, number>();
    const hucre = new Map<string, Map<string, GraphEdge>>();
    let enYogun = 0;
    for (const e of edges) {
      satirToplam.set(e.actor, (satirToplam.get(e.actor) ?? 0) + e.count);
      sutunToplam.set(e.module, (sutunToplam.get(e.module) ?? 0) + e.count);
      let satir = hucre.get(e.actor);
      if (!satir) hucre.set(e.actor, (satir = new Map()));
      satir.set(e.module, e);
      if (e.count > enYogun) enYogun = e.count;
    }
    const sirala = (m: Map<string, number>) =>
      [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "tr"));
    return {
      satirlar: sirala(satirToplam),
      sutunlar: sirala(sutunToplam),
      hucre,
      enYogun,
      kenarSayisi: edges.length,
    };
  }, [data]);

  if (isLoading) {
    return (
      <div
        aria-busy="true"
        aria-label="Isı matrisi yükleniyor"
        className="h-24 animate-pulse rounded-lg bg-muted"
      />
    );
  }

  // != null: openapi-fetch boş-gövdeli non-ok cevapta error="" (falsy!) verebilir —
  // truthiness kontrolü onu yutup sahte "dokunuş yok" basardı (RadarPage/GraphPage
  // ile aynı bulgu). data varken geçici poll hatası matrisi GİZLEMEZ.
  if (error != null && data === undefined) {
    return (
      <div role="alert" className="rounded-lg border border-severity-high/40 bg-severity-high/10 p-3 text-xs">
        <span className="font-medium text-severity-high">Isı matrisine ulaşılamıyor.</span>{" "}
        <span className="font-mono text-muted-foreground">{hataMesaji(error)}</span>
      </div>
    );
  }

  // BOŞ ≠ HATA: boş graf gerçek bir cevap ({window_days, nodes:[], edges:[]}).
  if (veri.kenarSayisi === 0) {
    return (
      <p className="rounded-lg border border-border bg-card p-4 text-xs text-muted-foreground">
        Bu pencerede dokunuş yok — matris, izlenen commit olaylarından dolar. Tek
        aktör/modül ya da hiç veri olmadığında burası dürüstçe böyle boş kalır.
      </p>
    );
  }

  const secilenKenar = secim ? (veri.hucre.get(secim.actor)?.get(secim.module) ?? null) : null;

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-3">
      <p className="text-[11px] text-muted-foreground">
        <span className="tabular-nums">{veri.satirlar.length}</span> aktör ×{" "}
        <span className="tabular-nums">{veri.sutunlar.length}</span> modül · derin
        inceleme (pencere seçimi, kenar detayı) için{" "}
        <Link to="/graph" className="underline hover:text-foreground">
          Dokunma grafı
        </Link>{" "}
        sayfasına bakabilirsiniz.
      </p>

      {/* Tailwind grid: sütun sayısı veriye bağlı olduğu için grid-template-columns
          INLINE style ile kuruluyor (JIT dinamik bracket değeri tarayamaz — sabit
          sınıf listesi ISI_SINIFLARI'nda olduğu gibi). Yeni kütüphane YOK. */}
      <div className="overflow-x-auto">
        <div
          role="group"
          aria-label="Aktör × modül dokunma matrisi (özet)"
          className="grid w-max gap-1"
          style={{
            gridTemplateColumns: `minmax(6rem,auto) repeat(${veri.sutunlar.length}, minmax(3.5rem, 1fr))`,
          }}
        >
          <div />
          {veri.sutunlar.map(([modul, toplam]) => (
            <div
              key={`col-${modul}`}
              className="flex flex-col items-center justify-end gap-0.5 px-1 pb-1"
            >
              <span
                title={modul}
                className="max-w-full truncate font-mono text-[10px] text-muted-foreground"
              >
                {modul}
              </span>
              <span className="text-[10px] tabular-nums text-muted-foreground">{toplam}</span>
            </div>
          ))}

          {veri.satirlar.map(([aktor, toplam]) => (
            <Fragment key={aktor}>
              <div className="flex items-center gap-2 py-1">
                <ActorChip handle={aktor} />
                <span className="text-[10px] tabular-nums text-muted-foreground">{toplam}</span>
              </div>
              {veri.sutunlar.map(([modul]) => {
                const kenar = veri.hucre.get(aktor)?.get(modul);
                if (!kenar) {
                  return (
                    <div key={`${aktor}-${modul}`} className="flex items-center justify-center">
                      <div className="h-8 w-full rounded bg-muted/20">
                        <span className="sr-only">
                          {aktor}, {modul}: dokunuş yok
                        </span>
                      </div>
                    </div>
                  );
                }
                const secili = secim?.actor === aktor && secim?.module === modul;
                return (
                  <div key={`${aktor}-${modul}`} className="flex items-center justify-center">
                    <button
                      type="button"
                      onClick={() =>
                        setSecim((s) =>
                          s && s.actor === aktor && s.module === modul ? null : { actor: aktor, module: modul },
                        )
                      }
                      aria-pressed={secili}
                      aria-label={`${aktor}, ${modul}: ${kenar.count} dokunuş — olay listesini aç`}
                      title={`${aktor} → ${modul}: ${kenar.count} dokunuş · son ${tarihMetni(kenar.last_ts)}`}
                      className={`flex h-8 w-full items-center justify-center rounded text-xs tabular-nums hover:brightness-125 ${isiSinifi(
                        kenar.count,
                        veri.enYogun,
                      )} ${kenar.is_active_declared ? "ring-2 ring-inset ring-foreground/70" : ""} ${
                        secili ? "outline outline-2 outline-offset-1 outline-foreground" : ""
                      }`}
                    >
                      {kenar.count}
                    </button>
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          Yoğunluk
          {ISI_SINIFLARI.map((cls, i) => (
            <span key={cls} aria-hidden className={`inline-block size-2.5 rounded-sm ${cls}`} title={`${i + 1}. kademe`} />
          ))}
        </span>
        <span className="inline-flex items-center gap-1">
          <span aria-hidden className="inline-block size-2.5 rounded-sm bg-primary/45 ring-2 ring-inset ring-foreground/70" />
          şu an beyanlı
        </span>
      </div>

      {secim && (
        <OlayListesi
          secim={secim}
          kenar={secilenKenar}
          eventsQ={eventsQ}
          onClose={() => setSecim(null)}
        />
      )}
    </div>
  );
}

function OlayListesi({
  secim,
  kenar,
  eventsQ,
  onClose,
}: {
  secim: Secim;
  kenar: GraphEdge | null;
  eventsQ: { data?: { events: NormalizedEvent[] }; error: unknown; isLoading: boolean };
  onClose: () => void;
}) {
  const olaylar = useMemo(() => {
    const tumu = eventsQ.data?.events ?? [];
    return tumu
      .filter((e) => e.actor === secim.actor && eventModules(e).has(secim.module))
      .sort((a, b) => parseUtc(b.ts).getTime() - parseUtc(a.ts).getTime());
  }, [eventsQ.data, secim]);

  return (
    <div className="space-y-2 rounded-lg border border-border bg-background p-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs">
          <ActorChip handle={secim.actor} /> <span aria-hidden>↳ </span>
          <span className="font-mono">{secim.module}</span>
          {kenar && (
            <span className="ml-2 text-[11px] text-muted-foreground">
              <span className="tabular-nums">{kenar.count}</span> dokunuş · son{" "}
              {tarihMetni(kenar.last_ts)}
            </span>
          )}
        </p>
        <button
          type="button"
          onClick={onClose}
          aria-label="Olay listesini kapat"
          className="rounded px-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          ✕
        </button>
      </div>

      {eventsQ.isLoading ? (
        <p className="text-xs text-muted-foreground" aria-busy="true">
          Olaylar yükleniyor…
        </p>
      ) : eventsQ.error != null && eventsQ.data === undefined ? (
        // != null: aynı openapi-fetch bulgusu — "" hata sessizce yutulmasın.
        <p role="alert" className="text-xs text-severity-high">
          Olay listesine ulaşılamadı — <span className="font-mono">{hataMesaji(eventsQ.error)}</span>
        </p>
      ) : olaylar.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Bu hücre için eşleşen olay bulunamadı — PR/issue kayıtları dosya listesi
          taşımaz (yalnız commit'ler modüle eşlenir) ya da olay akışı ayrı bir
          pencerede. Matristeki sayı yine de gerçek: bu bilgi eksikliği "dokunuş
          olmadı" anlamına gelmez.
        </p>
      ) : (
        <ul aria-label={`${secim.actor} → ${secim.module} olayları`} className="divide-y divide-border">
          {olaylar.map((e) => {
            const tur = TUR[e.type] ?? { etiket: e.type, ikon: "•" };
            return (
              <li key={e.id} className="flex items-center gap-2 py-1.5 text-xs">
                <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                  <span aria-hidden>{tur.ikon}</span> {tur.etiket}
                </span>
                <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground">
                  {e.branch ?? e.ref}
                </span>
                <span className="shrink-0 tabular-nums text-[11px] text-muted-foreground">
                  {tarihMetni(e.ts)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
