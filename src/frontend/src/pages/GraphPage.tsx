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
import { useGraph } from "../lib/useGraph";

type GraphEdge = components["schemas"]["GraphEdge"];
type GraphNode = components["schemas"]["GraphNode"];

/* Dokunma grafı sayfası (#105) — "kim nereye dokunuyor" tek-kare resmi.
   Görünüm: ısı matrisi (tasarım paketi /graph modu (b)) — aktör×modül, hücrede
   count DOĞRUDAN yazılı, tıkla → sağda kenar detayı.

   Ölçek kararı (tasarım paketi, erişilebilirlik): kırmızı-yeşil diverging YASAK
   (~%8 erkek renk körü okuyamaz) → background→primary TEK-TON ramp, 5 kademeye
   QUANTIZE (sürekli gradyan yerine: hücreler birbirine göre karşılaştırılabilir)
   + görünür legend. Renk asla tek kanal değil: sayı her hücrede yazılı,
   `is_active_declared` = halka (şekil), bayatlık = opaklık düşüşü.

   Gate'li (eksik DEĞİL, bilinçli): güç-yönlü graf görünümü (mod a) ve treemap
   (mod c) — ikisi de S3; çalışmayan sekme basmıyoruz (ölü link yok, AppLayout
   kuralı). Kenar başına dosya listesi de YOK: GraphEdge kontratı taşımıyor,
   uydurma alan çizilmez. */

/* Isı rampası — Tailwind JIT literal sınıf adı tarar, bu yüzden dinamik
   `bg-primary/${n}` KURULMAZ; tam sınıf adları sabit tabloda. */
const ISI_SINIFLARI = [
  "bg-primary/10 text-foreground",
  "bg-primary/25 text-foreground",
  "bg-primary/45 text-foreground",
  "bg-primary/70 text-primary-foreground",
  "bg-primary text-primary-foreground",
] as const;

const PENCERELER = [7, 14, 30] as const;
const GUN_MS = 86_400_000;

/** Hücrenin ısı sınıfı. Ölçek en yoğun hücreye GÖRECELİdir (legend bunu
    sayıyla söyler — gizli normalizasyon yok). İndeks daima kenetlenir:
    bozuk/0 bir `count` gelse bile className'e `undefined` sızmaz. */
function isiSinifi(count: number, enYogun: number): string {
  const oran = enYogun > 0 ? count / enYogun : 0;
  const k = Math.ceil(oran * ISI_SINIFLARI.length);
  const i = Math.min(ISI_SINIFLARI.length - 1, Math.max(0, k - 1));
  return ISI_SINIFLARI[i];
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
  const { data, error, isLoading, isFetching, dataUpdatedAt } = useGraph(pencere);

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

  // Hayalet-panel temizliği: seçili kenar veriden düşerse (pencere değişti,
  // dokunuş pencereden çıktı) panel dürüstçe kapanır — stale detay gösterilmez.
  useEffect(() => {
    if (secili && !seciliKenar) setSecili(null);
  }, [secili, seciliKenar]);

  useEffect(() => {
    if (!secili) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSecili(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [secili]);

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
