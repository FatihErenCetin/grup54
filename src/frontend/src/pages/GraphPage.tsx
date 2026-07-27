import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { components } from "../api/schema.d.ts";
import {
  ActorChip,
  EmptyState,
  HataDurumu,
  SonGuncelleme,
  YuklemeIskeleti,
} from "../components/ui";
import { ISI_SINIFLARI, isiSinifi } from "../lib/isiRampasi";
import { useGraph } from "../lib/useGraph";

type GraphEdge = components["schemas"]["GraphEdge"];
type GraphNode = components["schemas"]["GraphNode"];

/* Dokunma grafı sayfası (#105/#130) — "kim nereye dokunuyor" tek-kare resmi.
   İki çalışan görünüm modu (sekme ailesi, tercih localStorage'da kalıcı):
     - Isı matrisi (tasarım paketi /graph modu (b)) — aktör×modül, hücrede
       count DOĞRUDAN yazılı, tıkla → sağda kenar detayı.
     - Treemap (tasarım paketi /graph modu (c)) — alan = modülün toplam
       dokunuş sayısı, aynı ısı rampası dolgu, tıkla → sağda modül detayı
       (kim-dokunuyor avatarları).
   İkisi de AYNI TouchGraph cevabından (nodes+edges) türer — sıfır yeni endpoint.

   Ölçek kararı (tasarım paketi, erişilebilirlik): kırmızı-yeşil diverging YASAK
   (~%8 erkek renk körü okuyamaz) → background→primary TEK-TON ramp, 5 kademeye
   QUANTIZE (sürekli gradyan yerine: hücreler/modüller birbirine göre
   karşılaştırılabilir) + görünür legend. Renk asla tek kanal değil: sayı her
   hücrede/modülde yazılı, `is_active_declared` = halka (şekil), bayatlık =
   opaklık düşüşü.

   Gate'li (eksik DEĞİL, bilinçli — #130 GATE notu): güç-yönlü graf (mod a) ve
   git ağacı (mod d) sekme ailesine EKLENMEDİ (çalışmayan sekme basmıyoruz,
   ölü link yok — AppLayout kuralı):
     - Güç-yönlü: layout için yeni bir kütüphane gerektirir (d3-force ya da
       eşdeğeri); bu depoda bağımlılık ekleme yasağı var → S3 sonrasına gate.
     - Git ağacı: şerit/dirsek çizimi gerçek commit DAG'ı (parent_sha) ister;
       bugünkü kontrat bunu taşımıyor (Ek-B B6 ertelemesi) → uydurma bir ağaç
       çizmektense dürüstçe gate'li bırakıyoruz.
   Kenar başına dosya listesi de YOK: GraphEdge kontratı taşımıyor, uydurma
   alan çizilmez. */

const PENCERELER = [7, 14, 30] as const;
const GUN_MS = 86_400_000;

/* ── Görünüm modu (#130): sekme ailesi + localStorage kalıcılığı ─────────────
   Yalnızca ÇALIŞAN modlar burada — gate'li olanlar listeye girmiyor (yukarıdaki
   gerekçe). Üçüncü/dördüncü mod eklenince tek yapılacak şey bu diziye satır. */
const GORUNUM_MODLARI = [
  { id: "isi", etiket: "Isı matrisi" },
  { id: "treemap", etiket: "Treemap" },
] as const;
type GorunumModu = (typeof GORUNUM_MODLARI)[number]["id"];

const MOD_STORAGE_KEY = "grup54:graph:gorunum-modu";

function gecerliMod(deger: unknown): deger is GorunumModu {
  return GORUNUM_MODLARI.some((m) => m.id === deger);
}

/** localStorage okuması try/catch'siz ASLA yapılmaz: gizli-sekme/kota hatası
    sayfayı beyaz ekran ETMEZ, sessizce varsayılana düşer. */
function okunanMod(): GorunumModu {
  try {
    const ham = window.localStorage.getItem(MOD_STORAGE_KEY);
    if (gecerliMod(ham)) return ham;
  } catch {
    /* private mode / kota — varsayılana düş */
  }
  return "isi";
}

function modKaydet(mod: GorunumModu): void {
  try {
    window.localStorage.setItem(MOD_STORAGE_KEY, mod);
  } catch {
    /* kalıcılık best-effort — mod yine de state'te değişir, sayfa çalışır */
  }
}

/** Gün cinsinden yaş; tarih çözülemezse null (sessizce "bugün" SAYILMAZ). */
function gunYasi(iso: string, simdi: number): number | null {
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.max(0, (simdi - t) / GUN_MS);
}

/* Bayatlık = opaklık (tasarım paketi). Kademeler literal — JIT taraması için. */
function bayatlikSinifi(yas: number | null): string {
  if (yas === null || yas < 2) return "opacity-100";
  return yas < 7 ? "opacity-80" : "opacity-60";
}

function tarihMetni(iso: string): string {
  const t = new Date(iso).getTime();
  // Çözülemeyen tarih yutulmaz: ham değer basılır (uydurma tarih yok)
  return Number.isNaN(t) ? iso : new Date(t).toLocaleString("tr-TR");
}

/** Göreli yaş — DAİMA gerçek tarihin yanında ikincil olarak basılır
    (akan sahte sayaç yok, D-34; değer yalnız poll'da tazelenir). */
function yasMetni(yas: number | null): string {
  if (yas === null) return "tarih okunamadı";
  if (yas < 1) return "bugün";
  return `${Math.floor(yas)} gün önce`;
}

export default function GraphPage() {
  // undefined = parametresiz istek → backend KENDİ varsayılanını uygular.
  // Varsayılanı UI'da uydurmuyoruz; gerçek pencere data.window_days'ten okunur.
  const [pencere, setPencere] = useState<number | undefined>(undefined);
  const [secili, setSecili] = useState<{ actor: string; module: string } | null>(null);
  // Mod: lazy initializer → localStorage yalnız ilk mount'ta okunur (her render'da değil).
  const [mod, setModHam] = useState<GorunumModu>(okunanMod);
  const [seciliModul, setSeciliModul] = useState<string | null>(null);
  const { data, error, isLoading, isFetching, dataUpdatedAt } = useGraph(pencere);

  // Mod değişince her iki modun seçimi de temizlenir — kapalı moddan hayalet
  // panel kalmaz (isi'nin `secili`'si treemap'te anlamsız, tersi de öyle).
  function modSec(yeni: GorunumModu) {
    setModHam(yeni);
    modKaydet(yeni);
    setSecili(null);
    setSeciliModul(null);
  }

  // Türetimler erken-return'lerden ÖNCE (hook kuralı). `data` referansına
  // bağlı: her render'da yeniden dizi kurup memo'yu boşa düşürmüyoruz.
  const veri = useMemo(() => {
    const nodes: GraphNode[] = data?.nodes ?? [];
    const edges: GraphEdge[] = data?.edges ?? [];

    const satirToplam = new Map<string, number>();
    const sutunToplam = new Map<string, number>();
    const hucre = new Map<string, Map<string, GraphEdge>>();
    const modulAktorleri = new Map<string, Set<string>>();
    let enYogun = 0;
    let aktifSayisi = 0;

    // Önce düğümler: kenarsız bir düğüm gelirse satırı/sütunu yine de görünsün
    for (const n of nodes) {
      const hedef = n.type === "actor" ? satirToplam : sutunToplam;
      if (!hedef.has(n.id)) hedef.set(n.id, 0);
    }
    for (const e of edges) {
      // Savunma: `nodes`'ta geçmeyen bir kenar ucu SESSİZCE düşmesin — gerçek
      // bir dokunuşu gizlemektense ekstra satır/sütun çizmek dürüst olan.
      satirToplam.set(e.actor, (satirToplam.get(e.actor) ?? 0) + e.count);
      sutunToplam.set(e.module, (sutunToplam.get(e.module) ?? 0) + e.count);

      let satir = hucre.get(e.actor);
      if (!satir) hucre.set(e.actor, (satir = new Map()));
      satir.set(e.module, e);

      let aktorler = modulAktorleri.get(e.module);
      if (!aktorler) modulAktorleri.set(e.module, (aktorler = new Set()));
      aktorler.add(e.actor);

      if (e.count > enYogun) enYogun = e.count;
      if (e.is_active_declared) aktifSayisi += 1;
    }

    // Toplamlar GÖRÜNEN hücrelerden toplanır → kullanıcı elle toplayınca tutar.
    // (Kontratta GraphNode.weight de bu toplama eşit; çelişki basmamak için
    // tek kaynak olarak görünen veriyi kullanıyoruz.)
    const sirala = (m: Map<string, number>) =>
      [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "tr"));

    // Asıl sinyal: aynı modüle birden fazla aktör dokunmuşsa kesişim riski orada
    const paylasilan = new Set(
      [...modulAktorleri].filter(([, s]) => s.size > 1).map(([m]) => m),
    );

    return {
      satirlar: sirala(satirToplam),
      sutunlar: sirala(sutunToplam),
      hucre,
      modulAktorleri,
      enYogun,
      aktifSayisi,
      kenarSayisi: edges.length,
      paylasilan,
    };
  }, [data]);

  const seciliKenar = secili
    ? (veri.hucre.get(secili.actor)?.get(secili.module) ?? null)
    : null;
  const seciliModulVar = seciliModul !== null && veri.sutunlar.some(([m]) => m === seciliModul);

  // Hayalet-panel temizliği: seçili kenar/modül veriden düşerse (pencere
  // değişti, dokunuş pencereden çıktı) panel dürüstçe kapanır — stale detay
  // gösterilmez. İki mod ayrı state ama aynı kurala tabi.
  useEffect(() => {
    if (secili && !seciliKenar) setSecili(null);
  }, [secili, seciliKenar]);

  useEffect(() => {
    if (seciliModul && !seciliModulVar) setSeciliModul(null);
  }, [seciliModul, seciliModulVar]);

  useEffect(() => {
    if (!secili && !seciliModul) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSecili(null);
        setSeciliModul(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [secili, seciliModul]);

  // Yaşlar son BAŞARILI verinin anına sabitlenir (SonGuncelleme ile aynı an);
  // render zamanına bağlasaydık sekme arka plandayken sessizce kayardı.
  const simdi = dataUpdatedAt || Date.now();
  // Seçili pencere: kullanıcı seçmediyse cevabın kendi söylediği gerçek pencere.
  const etkinPencere = pencere ?? data?.window_days;

  /* Üç durum: başlık + pencere seçici HER durumda görünür kalır (yükleme
     iskeleti tüm sayfayı yutarsa kullanıcı yeni tıkladığı kontrolü kaybeder),
     üç durumun kendisi gövdede çizilir. Sıra ve semantik RadarPage ile aynı:
     yükleniyor → (hata VE veri yok) → boş → içerik. */
  let govde: ReactNode;
  if (isLoading) {
    govde = <YuklemeIskeleti label="Dokunma grafı yükleniyor" satir={4} />;
  } else if (error != null && data === undefined) {
    // != null: openapi-fetch boş-gövdeli non-ok cevapta error="" (falsy!)
    // verebilir — truthiness kontrolü onu yutup sahte "graf boş" basardı.
    // data varken geçici poll hatası matrisi GİZLEMEZ (polling sürüyor).
    govde = <HataDurumu baslik="Dokunma grafına ulaşılamıyor" hata={error} />;
  } else if (veri.kenarSayisi === 0) {
    // BOŞ ≠ HATA: boş graf gerçek bir cevap ({window_days, nodes:[], edges:[]}).
    govde = (
      <EmptyState
        title="Bu pencerede dokunuş yok"
        description="Aktör×modül matrisi, izlenen commit/PR olaylarından ve .harness/active beyanlarından dolar. Seçili zaman penceresinde henüz kayıt yok."
        items={[
          "Satır = aktör (insan ya da AI ajanı), sütun = modül",
          "Hücredeki sayı = o modüle dokunan olay sayısı",
          "Halkalı hücre = şu an .harness/active'da beyanlı",
        ]}
        eta="Pencereyi genişletmeyi dene; veri ingest'ten gelir (#104)."
      />
    );
  } else if (mod === "treemap") {
    govde = (
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1 space-y-3">
          <Ozet veri={veri} />
          <TreemapGorunumu
            veri={veri}
            seciliModul={seciliModul}
            onSec={(modul) => setSeciliModul((s) => (s === modul ? null : modul))}
          />
          <TreemapLegend enYogunModul={veri.sutunlar[0]?.[1] ?? 0} />
        </div>
        {seciliModulVar && seciliModul && (
          <ModulPaneli
            modul={seciliModul}
            modulToplam={veri.sutunlar.find(([m]) => m === seciliModul)?.[1] ?? 0}
            aktorler={[...(veri.modulAktorleri.get(seciliModul) ?? [])]
              .map((a) => ({ aktor: a, kenar: veri.hucre.get(a)?.get(seciliModul) }))
              .filter((x): x is { aktor: string; kenar: GraphEdge } => x.kenar !== undefined)
              .sort((a, b) => b.kenar.count - a.kenar.count)}
            simdi={simdi}
            onClose={() => setSeciliModul(null)}
          />
        )}
      </div>
    );
  } else {
    govde = (
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1 space-y-3">
          <Ozet veri={veri} />
          <Matris
            veri={veri}
            secili={secili}
            simdi={simdi}
            onSec={(actor, modul) =>
              setSecili((s) =>
                s && s.actor === actor && s.module === modul
                  ? null
                  : { actor, module: modul },
              )
            }
          />
          <Legend enYogun={veri.enYogun} />
        </div>
        {seciliKenar && secili && (
          <KenarPaneli
            kenar={seciliKenar}
            simdi={simdi}
            aktorToplam={veri.satirlar.find(([a]) => a === secili.actor)?.[1] ?? 0}
            modulToplam={veri.sutunlar.find(([m]) => m === secili.module)?.[1] ?? 0}
            digerAktorler={[...(veri.modulAktorleri.get(secili.module) ?? [])].filter(
              (a) => a !== secili.actor,
            )}
            onClose={() => setSecili(null)}
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-base font-semibold">Dokunma grafı</h1>
        <SonGuncelleme dataUpdatedAt={dataUpdatedAt} isFetching={isFetching} />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1" role="tablist" aria-label="Görünüm modu">
          {GORUNUM_MODLARI.map((m) => (
            <button
              key={m.id}
              type="button"
              role="tab"
              aria-selected={m.id === mod}
              onClick={() => modSec(m.id)}
              className={`rounded px-2 py-1 text-xs font-medium ${
                m.id === mod
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted/50"
              }`}
            >
              {m.etiket}
            </button>
          ))}
        </div>
        {/* Gate'li modlar (#130): dead-tab basmıyoruz, gerekçe görünür kalsın */}
        <span
          className="text-[11px] text-muted-foreground"
          title="Güç-yönlü: yeni kütüphane gerektirir (bağımlılık yasağı). Git ağacı: gerçek commit DAG'ı (parent_sha) ister, bugünkü kontrat taşımıyor."
        >
          Güç-yönlü ve git ağacı gate'li — bkz. #130
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1" role="group" aria-label="Zaman penceresi">
          {PENCERELER.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPencere(p)}
              aria-pressed={p === etkinPencere}
              className={`rounded px-2 py-1 text-xs ${
                p === etkinPencere
                  ? "bg-muted font-medium"
                  : "text-muted-foreground hover:bg-muted/50"
              }`}
            >
              {p} gün
            </button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">
          {data
            ? `Son ${data.window_days} günlük pencere`
            : "Pencere cevapla birlikte gelir"}
        </span>
      </div>

      {govde}
    </div>
  );
}

/* ── Alt bileşenler: bu sayfaya özel, ortak tasarım dili ui.tsx'ten ────────── */

type Veri = {
  satirlar: [string, number][];
  sutunlar: [string, number][];
  hucre: Map<string, Map<string, GraphEdge>>;
  modulAktorleri: Map<string, Set<string>>;
  enYogun: number;
  aktifSayisi: number;
  kenarSayisi: number;
  paylasilan: Set<string>;
};

/** Matrisin cevapladığı soruyu tek cümlede söyler — grid'i kullanıcının
    kendi okumasına bırakmıyoruz. Hepsi gerçek veriden türetilir. */
function Ozet({ veri }: { veri: Veri }) {
  const { satirlar, sutunlar, paylasilan, aktifSayisi, kenarSayisi } = veri;
  let okuma: string;
  if (paylasilan.size > 0) {
    okuma = `${paylasilan.size} modüle birden fazla aktör dokundu (⇄) — kesişim riski orada.`;
  } else if (satirlar.length <= 1) {
    okuma =
      "Tek aktör görünüyor — kesişim (aynı modüle iki kişi) ancak ikinci bir aktör dokununca ortaya çıkar.";
  } else {
    okuma = "Aktörler ayrı modüllerde — bu pencerede kesişen modül yok.";
  }
  return (
    <p className="text-xs text-muted-foreground">
      <span className="tabular-nums">{satirlar.length}</span> aktör ×{" "}
      <span className="tabular-nums">{sutunlar.length}</span> modül ·{" "}
      <span className="tabular-nums">{kenarSayisi}</span> dokunma ilişkisi
      {aktifSayisi > 0 && (
        <>
          {" · "}
          <span className="tabular-nums">{aktifSayisi}</span> tanesi şu an beyanlı
        </>
      )}
      <br />
      {okuma}
    </p>
  );
}

function Matris({
  veri,
  secili,
  simdi,
  onSec,
}: {
  veri: Veri;
  secili: { actor: string; module: string } | null;
  simdi: number;
  onSec: (actor: string, modul: string) => void;
}) {
  const { satirlar, sutunlar, hucre, enYogun, paylasilan } = veri;
  return (
    // Geniş matris KENDİ kabında yatay kayar; sayfa gövdesi yatay kaymaz.
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      {/* Matris = tablo (div-grid değil): ekran okuyucu "enes, backend, 2"
          diye okur, satır/sütun başlığı ilişkisi bedavaya gelir. */}
      <table className="border-separate border-spacing-1 p-2">
        <caption className="sr-only">
          Aktör × modül dokunma matrisi. Hücre değeri, o aktörün o modüle
          dokunduğu olay sayısıdır.
        </caption>
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky left-0 z-10 bg-card px-2 text-left text-[11px] font-medium text-muted-foreground"
            >
              Aktör \ Modül
            </th>
            {sutunlar.map(([modul, toplam]) => (
              <th key={modul} scope="col" className="align-bottom">
                <div className="flex w-16 flex-col items-center gap-0.5">
                  <span
                    title={modul}
                    className={`max-w-full truncate font-mono text-[11px] ${
                      paylasilan.has(modul) ? "text-foreground" : "text-muted-foreground"
                    }`}
                  >
                    {modul}
                  </span>
                  <span className="text-[10px] tabular-nums text-muted-foreground">
                    {paylasilan.has(modul) && (
                      <span title="Birden fazla aktör dokundu">⇄ </span>
                    )}
                    {toplam}
                  </span>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {satirlar.map(([aktor, toplam]) => (
            <tr key={aktor}>
              <th
                scope="row"
                className="sticky left-0 z-10 bg-card px-2 text-left font-normal"
              >
                <div className="flex items-center gap-2 whitespace-nowrap">
                  <ActorChip handle={aktor} />
                  <span className="text-[10px] tabular-nums text-muted-foreground">
                    {toplam}
                  </span>
                </div>
              </th>
              {sutunlar.map(([modul]) => {
                const kenar = hucre.get(aktor)?.get(modul);
                if (!kenar) {
                  return (
                    <td key={modul} className="p-0">
                      <div className="h-9 w-16 rounded bg-muted/20">
                        <span className="sr-only">
                          {aktor}, {modul}: dokunuş yok
                        </span>
                      </div>
                    </td>
                  );
                }
                const yas = gunYasi(kenar.last_ts, simdi);
                const isSecili = secili?.actor === aktor && secili?.module === modul;
                return (
                  <td key={modul} className="p-0">
                    <button
                      type="button"
                      onClick={() => onSec(aktor, modul)}
                      aria-pressed={isSecili}
                      title={`${aktor} → ${modul}: ${kenar.count} dokunuş · son ${tarihMetni(
                        kenar.last_ts,
                      )}${kenar.is_active_declared ? " · şu an beyanlı" : ""}`}
                      className={`flex h-9 w-16 cursor-pointer items-center justify-center rounded text-xs tabular-nums hover:brightness-125 ${isiSinifi(
                        kenar.count,
                        enYogun,
                      )} ${bayatlikSinifi(yas)} ${
                        // is_active_declared = HALKA (şekil kanalı) + kalın sayı
                        kenar.is_active_declared
                          ? "font-semibold ring-2 ring-inset ring-foreground/70"
                          : ""
                      } ${
                        isSecili
                          ? "outline outline-2 outline-offset-1 outline-foreground"
                          : ""
                      }`}
                    >
                      <span aria-hidden>{kenar.count}</span>
                      <span className="sr-only">
                        {aktor}, {modul}: {kenar.count} dokunuş
                        {kenar.is_active_declared ? ", şu an beyanlı" : ""}, son{" "}
                        {tarihMetni(kenar.last_ts)}
                      </span>
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Legend zorunlu: quantize edilmiş ölçek görünür değilse renk okunamaz. */
function Legend({ enYogun }: { enYogun: number }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        Yoğunluk
        <span className="tabular-nums">1</span>
        {ISI_SINIFLARI.map((cls, i) => (
          <span
            key={cls}
            aria-hidden
            className={`inline-block size-3 rounded-sm ${cls}`}
            title={`${i + 1}. kademe (en yoğun hücreye göre)`}
          />
        ))}
        <span className="tabular-nums">{enYogun}</span>
        dokunuş
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block size-3 rounded-sm bg-primary/45 ring-2 ring-inset ring-foreground/70"
        />
        şu an beyanlı
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block size-3 rounded-sm bg-primary/45 opacity-60"
        />
        7+ gün önce (solar)
      </span>
    </div>
  );
}

/* ── Treemap (#130 mod c) ────────────────────────────────────────────────────
   Alan = modülün TOPLAM dokunuş sayısı (görünen kenarlardan toplanır — Isı
   matrisi'yle aynı `veri.sutunlar` kaynağı, uydurma ikinci bir sayı yok).
   Yerleşim: özyinelemeli ikili bölme ("slice-and-dice"), her adımda kümülatif
   değeri yarıya en yakından kesip UZUN kenar boyunca böler — d3-force/d3-hierarchy
   gibi yeni bir kütüphane GEREKMEZ (bağımlılık yasağı), köşegen oranları
   tam-squarify kadar kare değildir ama alan oranı HER ZAMAN doğrudur (test
   edilir: kapsama + üst-üste binmeme). */

type TreemapGirdi = { modul: string; deger: number };
type TreemapKutu = TreemapGirdi & { x: number; y: number; w: number; h: number };

export function treemapDizilimi(
  girdiler: TreemapGirdi[],
  x: number,
  y: number,
  w: number,
  h: number,
): TreemapKutu[] {
  if (girdiler.length === 0 || w <= 0 || h <= 0) return [];
  if (girdiler.length === 1) {
    return [{ ...girdiler[0], x, y, w, h }];
  }

  const sirali = [...girdiler].sort((a, b) => b.deger - a.deger);
  const toplam = sirali.reduce((s, g) => s + Math.max(g.deger, 0), 0);

  // Değersiz grup (hepsi 0/negatif — gerçekte olmamalı, count>=1 kontratla
  // gelir): eşit böl, NaN/Infinity üretmemek için savunma.
  if (toplam <= 0) {
    const kesit = Math.max(1, Math.floor(sirali.length / 2));
    const solEsit = sirali.slice(0, kesit).map((g) => ({ ...g, deger: 1 }));
    const sagEsit = sirali.slice(kesit).map((g) => ({ ...g, deger: 1 }));
    return w >= h
      ? [
          ...treemapDizilimi(solEsit, x, y, w / 2, h),
          ...treemapDizilimi(sagEsit, x + w / 2, y, w / 2, h),
        ]
      : [
          ...treemapDizilimi(solEsit, x, y, w, h / 2),
          ...treemapDizilimi(sagEsit, x, y + h / 2, w, h / 2),
        ];
  }

  // Kümülatif değeri yarıya en yakın noktadan kes (en az 1 eleman her tarafta).
  let kumulatif = 0;
  let kesit = 1;
  for (let i = 0; i < sirali.length; i++) {
    kumulatif += sirali[i].deger;
    if (kumulatif >= toplam / 2) {
      kesit = i + 1;
      break;
    }
  }
  kesit = Math.min(Math.max(kesit, 1), sirali.length - 1);

  const sol = sirali.slice(0, kesit);
  const sag = sirali.slice(kesit);
  const solToplam = sol.reduce((s, g) => s + g.deger, 0);
  const oran = solToplam / toplam;

  if (w >= h) {
    // Uzun kenar YATAY → dikey kesim (sol/sağ)
    const solGenislik = w * oran;
    return [
      ...treemapDizilimi(sol, x, y, solGenislik, h),
      ...treemapDizilimi(sag, x + solGenislik, y, w - solGenislik, h),
    ];
  }
  // Uzun kenar DİKEY → yatay kesim (üst/alt)
  const solYukseklik = h * oran;
  return [
    ...treemapDizilimi(sol, x, y, w, solYukseklik),
    ...treemapDizilimi(sag, x, y + solYukseklik, w, h - solYukseklik),
  ];
}

/** Modülün en son dokunuş anı + `is_active_declared` bayrağı — kenarları
    (edge) module bazında özetler, ikinci bir uydurma alan EKLEMEZ. */
function modulOzeti(
  veri: Veri,
  modul: string,
): { sonTs: string | null; aktifBeyanli: boolean } {
  let sonTs: string | null = null;
  let sonT = -Infinity;
  let aktifBeyanli = false;
  for (const aktor of veri.modulAktorleri.get(modul) ?? []) {
    const kenar = veri.hucre.get(aktor)?.get(modul);
    if (!kenar) continue;
    if (kenar.is_active_declared) aktifBeyanli = true;
    const t = new Date(kenar.last_ts).getTime();
    if (!Number.isNaN(t) && t > sonT) {
      sonT = t;
      sonTs = kenar.last_ts;
    }
  }
  return { sonTs, aktifBeyanli };
}

function TreemapGorunumu({
  veri,
  seciliModul,
  onSec,
}: {
  veri: Veri;
  seciliModul: string | null;
  onSec: (modul: string) => void;
}) {
  const { sutunlar, modulAktorleri, paylasilan } = veri;
  const enYogunModul = sutunlar[0]?.[1] ?? 0;
  // Nominal tuval — gerçek konteyner genişliği/yüksekliği ne olursa olsun
  // % dönüşü doğru orantıyı korur (yalnız köşegen estetiği bu orana göre karar verir).
  const kutular = useMemo(
    () =>
      treemapDizilimi(
        sutunlar.map(([modul, deger]) => ({ modul, deger })),
        0,
        0,
        1000,
        420,
      ),
    [sutunlar],
  );

  return (
    <div
      role="group"
      aria-label="Modül treemap'i — alan toplam dokunuş sayısı"
      className="relative h-72 w-full overflow-hidden rounded-lg border border-border bg-card sm:h-96"
    >
      {kutular.map((k) => {
        const yuzdeGenislik = (k.w / 1000) * 100;
        const yuzdeYukseklik = (k.h / 420) * 100;
        const { sonTs, aktifBeyanli } = modulOzeti(veri, k.modul);
        const yas = sonTs ? gunYasi(sonTs, Date.now()) : null;
        const isSecili = seciliModul === k.modul;
        // Çok küçük hücrede isim/avatar SIĞMAZ — dürüstçe sayıyla yetin
        // (uydurma etiket taşırmaktansa boş bırakmak daha az yanıltıcı).
        const kompakt = yuzdeGenislik < 10 || yuzdeYukseklik < 16;
        const aktorler = [...(modulAktorleri.get(k.modul) ?? [])];
        return (
          <button
            key={k.modul}
            type="button"
            aria-pressed={isSecili}
            title={`${k.modul}: ${k.deger} dokunuş, ${aktorler.length} aktör${
              aktifBeyanli ? " · şu an beyanlı" : ""
            }`}
            onClick={() => onSec(k.modul)}
            style={{
              left: `${(k.x / 1000) * 100}%`,
              top: `${(k.y / 420) * 100}%`,
              width: `${yuzdeGenislik}%`,
              height: `${yuzdeYukseklik}%`,
              padding: 2,
            }}
            className="absolute box-border"
          >
            <span
              className={`flex h-full w-full cursor-pointer flex-col items-center justify-center gap-1 overflow-hidden rounded p-1 text-left hover:brightness-125 ${isiSinifi(
                k.deger,
                enYogunModul,
              )} ${bayatlikSinifi(yas)} ${
                aktifBeyanli ? "ring-2 ring-inset ring-foreground/70" : ""
              } ${isSecili ? "outline outline-2 outline-offset-1 outline-foreground" : ""}`}
            >
              {!kompakt && (
                <span
                  className={`max-w-full truncate font-mono text-[11px] ${
                    paylasilan.has(k.modul) ? "font-semibold" : ""
                  }`}
                >
                  {paylasilan.has(k.modul) && <span aria-hidden>⇄ </span>}
                  {k.modul}
                </span>
              )}
              <span className="text-xs font-semibold tabular-nums">{k.deger}</span>
              {!kompakt && aktorler.length > 0 && (
                <span className="flex max-w-full flex-wrap items-center justify-center gap-1">
                  {aktorler.slice(0, 3).map((a) => (
                    <ActorChip key={a} handle={a} />
                  ))}
                  {aktorler.length > 3 && (
                    <span className="text-[10px] tabular-nums">
                      +{aktorler.length - 3}
                    </span>
                  )}
                </span>
              )}
              <span className="sr-only">
                {k.modul}: {k.deger} dokunuş, {aktorler.length} aktör
                {aktifBeyanli ? ", şu an beyanlı" : ""}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** Treemap'e özel legend: aynı ısı rampası, birim "modül" (Isı matrisi'nde
    "hücre") — iki görünüm aynı sözlüğü konuşur ama neyi ölçtüğünü doğru söyler. */
function TreemapLegend({ enYogunModul }: { enYogunModul: number }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        Yoğunluk
        <span className="tabular-nums">1</span>
        {ISI_SINIFLARI.map((cls, i) => (
          <span
            key={cls}
            aria-hidden
            className={`inline-block size-3 rounded-sm ${cls}`}
            title={`${i + 1}. kademe (en yoğun modüle göre)`}
          />
        ))}
        <span className="tabular-nums">{enYogunModul}</span>
        dokunuş · alan = modülün toplam dokunuşu
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block size-3 rounded-sm bg-primary/45 ring-2 ring-inset ring-foreground/70"
        />
        şu an beyanlı
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block size-3 rounded-sm bg-primary/45 opacity-60"
        />
        7+ gün önce (solar)
      </span>
    </div>
  );
}

function KenarPaneli({
  kenar,
  simdi,
  aktorToplam,
  modulToplam,
  digerAktorler,
  onClose,
}: {
  kenar: GraphEdge;
  simdi: number;
  aktorToplam: number;
  modulToplam: number;
  digerAktorler: string[];
  onClose: () => void;
}) {
  const yas = gunYasi(kenar.last_ts, simdi);
  return (
    <aside
      aria-label="Dokunuş detayı"
      // Ölçü DetailSheet ile aynı (w-[380px]): sekme değiştirince sağdan açılan
      // panel yerinden oynamasın. Matris kendi kabında yatay kayıyor, daralmıyor.
      className="sticky top-0 flex max-h-[calc(100vh-7rem)] w-[380px] shrink-0 flex-col gap-4 self-start overflow-y-auto rounded-lg border border-border bg-card p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <ActorChip handle={kenar.actor} />
          <p className="font-mono text-xs">
            <span aria-hidden>↳ </span>
            {kenar.module}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Detayı kapat"
          className="rounded px-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          ✕
        </button>
      </div>

      {kenar.is_active_declared && (
        <p className="rounded border border-primary/40 bg-primary/10 px-2 py-1.5 text-xs">
          <span aria-hidden>◎ </span>Şu an{" "}
          <code className="font-mono">.harness/active</code>'da beyanlı — bu modül
          canlı işaretli.
        </p>
      )}

      <div className="space-y-2.5">
        {/* ALL-CAPS yasak (D-34, TR İ/ı tuzağı) — hiyerarşi punto + ağırlık + renkle */}
        <h3 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
          Dokunuş
        </h3>
        <p className="text-sm leading-relaxed">
          <span className="tabular-nums">{kenar.count}</span> olayda bu modüle
          dokunuldu.
        </p>
        <p className="font-mono text-[11px] leading-relaxed text-muted-foreground">
          son: {tarihMetni(kenar.last_ts)}
          <br />
          {yasMetni(yas)}
        </p>
      </div>

      <div className="space-y-2.5">
        <h3 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
          Bağlam
        </h3>
        <p className="text-xs leading-relaxed text-muted-foreground">
          <span className="font-mono">{kenar.actor}</span> bu pencerede toplam{" "}
          <span className="tabular-nums">{aktorToplam}</span> dokunuş yaptı ·{" "}
          <span className="font-mono">{kenar.module}</span> toplam{" "}
          <span className="tabular-nums">{modulToplam}</span> dokunuş aldı.
        </p>
        {digerAktorler.length > 0 ? (
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">
              Aynı modüle dokunan diğer aktörler:
            </p>
            <div className="flex flex-wrap gap-2">
              {digerAktorler.map((a) => (
                <ActorChip key={a} handle={a} />
              ))}
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Bu modüle bu pencerede başka aktör dokunmadı.
          </p>
        )}
      </div>

      <div className="mt-auto space-y-1.5 border-t border-border pt-3">
        <p className="text-[10px] leading-snug text-muted-foreground">
          Dosya kırılımı yok: <code className="font-mono">GET /graph</code> kenar
          başına dosya listesi taşımıyor (modül, path'ten hesaplanır). Uydurma alan
          basmıyoruz.
        </p>
        <p className="font-mono text-[10px] text-muted-foreground">Esc kapat</p>
      </div>
    </aside>
  );
}

/** Treemap'in modül-seviyeli detay paneli — KenarPaneli'nin eşdeğeri (aynı
    380px ölçü, aynı yerleşim dili) ama tek kenar değil, o modüle dokunan TÜM
    aktörlerin dökümü ("kim-dokunuyor" — #130 kabul kriteri). */
function ModulPaneli({
  modul,
  modulToplam,
  aktorler,
  simdi,
  onClose,
}: {
  modul: string;
  modulToplam: number;
  aktorler: { aktor: string; kenar: GraphEdge }[];
  simdi: number;
  onClose: () => void;
}) {
  return (
    <aside
      aria-label="Modül detayı"
      className="sticky top-0 flex max-h-[calc(100vh-7rem)] w-[380px] shrink-0 flex-col gap-4 self-start overflow-y-auto rounded-lg border border-border bg-card p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 truncate font-mono text-sm font-semibold">{modul}</p>
        <button
          type="button"
          onClick={onClose}
          aria-label="Detayı kapat"
          className="rounded px-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          ✕
        </button>
      </div>

      <p className="text-sm leading-relaxed">
        Bu pencerede <span className="tabular-nums">{modulToplam}</span> dokunuş ·{" "}
        <span className="tabular-nums">{aktorler.length}</span> aktör.
      </p>

      <div className="space-y-2.5">
        <h3 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
          Kim dokunuyor
        </h3>
        <ul className="space-y-2">
          {aktorler.map(({ aktor, kenar }) => {
            const yas = gunYasi(kenar.last_ts, simdi);
            return (
              <li
                key={aktor}
                className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1.5"
              >
                <ActorChip handle={aktor} />
                <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  {kenar.is_active_declared && (
                    <span title="Şu an .harness/active'da beyanlı" aria-hidden>
                      ◎
                    </span>
                  )}
                  <span className="tabular-nums">{kenar.count}</span>
                  <span>· {yasMetni(yas)}</span>
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="mt-auto space-y-1.5 border-t border-border pt-3">
        <p className="text-[10px] leading-snug text-muted-foreground">
          Alan = toplam dokunuş (görünen kenarlardan toplanır); dosya kırılımı
          yok, aynı gerekçe ısı matrisiyle ortak (GraphEdge kontratı taşımıyor).
        </p>
        <p className="font-mono text-[10px] text-muted-foreground">Esc kapat</p>
      </div>
    </aside>
  );
}
