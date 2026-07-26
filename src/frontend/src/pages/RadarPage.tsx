import { useEffect, useRef, useState } from "react";
import type { components } from "../api/schema.d.ts";
import { DetailSheet } from "../components/DetailSheet";
import { FeedItem } from "../components/FeedItem";
import { PresenceStrip } from "../components/PresenceStrip";
import { EmptyState, HataDurumu, SonGuncelleme, YuklemeIskeleti } from "../components/ui";
import { useRadar } from "../lib/useRadar";

type SeverityFilter = "hepsi" | "high" | "med" | "low";

const FILTERS: { key: SeverityFilter; label: string }[] = [
  { key: "hepsi", label: "Hepsi" },
  { key: "high", label: "▲ yüksek" },
  { key: "med", label: "◆ orta" },
  { key: "low", label: "● düşük" },
];

type RadarDegraded = components["schemas"]["RadarDegraded"];

/* #252 — "sessiz eksiltme"nin panzehiri. `degraded` DOLU demek: bu turda bazı
   çiftler judge'a ulaşılamadığı için HİÇ yargılanamadı; liste kısa çünkü sonuç
   eksik, çakışma yok olduğu için değil.
   Bilinçli olarak tespit dili KULLANILMAZ (severity rozeti · confidence · aktör
   çipi yok, liste dışında durur): bu bir tespit kartı değil, "elimizdeki sonuç
   eksik" uyarısıdır — tespit gibi görünürse sayılır, sayılırsa yine yalan olur.
   Renk tek başına anlam taşımaz (D-34) → ⚠ ikon + Türkçe metin birlikte. */
function EksikSonucSeridi({ degraded }: { degraded: RadarDegraded }) {
  const eksik = degraded.judge_unavailable;
  const degerlendirilen = degraded.evaluated;
  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-lg border border-severity-med/40 bg-severity-med/10 p-4"
    >
      <span aria-hidden className="mt-0.5 shrink-0 text-severity-med">
        ⚠
      </span>
      <div className="min-w-0 space-y-1">
        <p className="text-sm font-medium">
          Sonuç eksik — <span className="tabular-nums">{eksik}</span> çift
          değerlendirilemedi
        </p>
        <p className="text-xs leading-relaxed text-muted-foreground">
          AI değerlendiriciye (judge) ulaşılamadı: bu turda{" "}
          <span className="tabular-nums">{degerlendirilen}</span> çift
          değerlendirildi, <span className="tabular-nums">{eksik}</span> çift hiç
          yargılanamadı. O çiftlerde çakışma{" "}
          <span className="font-medium text-foreground">olmadığı için değil</span>,
          judge erişilemediği için liste kısa — aşağıdakini eksiksiz sayma.
        </p>
        <p className="text-[11px] text-muted-foreground">
          Bu bir tespit değil, sonucun eksik olduğunu söyleyen uyarıdır. Polling
          sürüyor; judge dönünce eksik çiftler kendiliğinden değerlendirilir.
        </p>
      </div>
    </div>
  );
}

/* Radar sayfası (#21) — "AI-grading görünür yüz": severity + confidence +
   TR judge-rationale jüriye burada görünür.
   Gate'li (eksik DEĞİL, bilinçli — PR gövdesi + tasarım paketi "cila tuzağı"):
   Aktif/Drift/Çözüldü sekmeleri (status S3, Ek B1) · aksiyon butonları
   (yazma ucu B6 ertelemesi) · yaş (first_seen_at S3) · "N yeni" pili (B2) ·
   locks gösterimi (.harness/locks henüz yok).
   Bilinçli tasarım sapması: paketteki boş durum "kurulum checklist'i"ydi —
   backend bağlıyken doğru boş durum "radar temiz"dir; checklist onboarding'e
   (S3 sihirbaz) ait.
   Sonradan eklenenler: #252 eksik-sonuç şeridi (yukarıda) · #158 düşük-güven
   tespitlerin katlanmış bölümü (varsayılan kapalı). */
export default function RadarPage() {
  const { data, isLoading, isFetching, dataUpdatedAt, error } = useRadar();
  const [filter, setFilter] = useState<SeverityFilter>("hepsi");
  // Seçim ID ile tutulur: polling'de nesne referansı tazelenir, ID kalıcıdır;
  // tespit listeden düşerse panel dürüstçe kapanır (stale detay gösterilmez)
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // #158: katlanan bölüm VARSAYILAN KAPALI (düşük-güven gürültüsü yüksek/orta
  // sinyali bastırmasın); açık kalması kullanıcı kararı, oturum boyu korunur
  const [dusukAcik, setDusukAcik] = useState(false);

  // Erken-return'lerden ÖNCE (hook kuralı). Görünür liste burada da türetilir;
  // aşağıdaki render bloğu aynı ifadeyi kullanır.
  const detections = data?.detections ?? [];
  // #252: mutlu yolda alan null/undefined → şerit hiç çizilmez. judge_unavailable=0
  // gelirse de çizmiyoruz: "0 çift değerlendirilemedi" uyarısı gürültüdür.
  const degraded =
    data?.degraded && data.degraded.judge_unavailable > 0 ? data.degraded : null;
  const visible =
    filter === "hepsi" ? detections : detections.filter((d) => d.severity === filter);

  // #158 ayrımı: KATLANAN bölüm yalnız kullanıcı düşükleri özellikle istemediğinde
  // devrede. "● düşük" filtresi seçiliyken katlamak, istenen şeyi saklamak olurdu.
  const dusukKatlanir = filter !== "low";
  const anaListe = dusukKatlanir ? visible.filter((d) => d.severity !== "low") : visible;
  const dusukler = dusukKatlanir ? visible.filter((d) => d.severity === "low") : [];

  // Roving focus: klavye gezinmesinde focus ring secimi TAKIP eder (dogrulama
  // bulgusu: ring eski satirda kalinca en baskin vurgu yanlis satiri gosteriyordu)
  const rowRefs = useRef(new Map<string, HTMLButtonElement>());
  // dusukAcik da bağımlılık: katlanan bölüme adım atıldığında satır BİR SONRAKİ
  // render'da mount olur; yalnız [selectedId]'e bakan efekt o an haritada satırı
  // bulamayıp focus'u eski satırda bırakıyordu (test dump'ında yakalandı).
  useEffect(() => {
    if (selectedId) rowRefs.current.get(selectedId)?.focus();
  }, [selectedId, dusukAcik]);

  // Hayalet-panel temizligi: secili tespit gorunurden dusunce state de temizlenir
  // (yalniz gorunumu null'lamak, filtre gidis-donusunde paneli tiklamasiz geri
  // acyordu — canli dogrulama bulgusu)
  useEffect(() => {
    if (selectedId && !visible.some((d) => d.id === selectedId)) setSelectedId(null);
  }, [selectedId, visible]);

  // #158 + klavye: ↑↓ katlanmış bölüme adım atarsa bölüm AÇILIR. Alternatifi
  // (nav'ı katlanan satırlarda durdurmak) klavye kullanıcısına düşükleri hiç
  // ulaştırmazdı; roving focus da mount'suz satıra focus edemez.
  // Bölümü elle kapatmak seçimi de temizlediği için (aşağıdaki toggle) burası
  // "kapanmayan bölüm" döngüsü üretmez.
  useEffect(() => {
    if (!selectedId) return;
    const secili = visible.find((d) => d.id === selectedId);
    if (secili?.severity === "low") setDusukAcik(true);
  }, [selectedId, visible]);

  // Klavye (tasarım MOGXv "↑↓ gezin · Esc kapat"): yalnız panel açıkken aktif.
  // Ilerletme functional-update ile: hizli ardisik tuslamada stale-closure'in
  // adim yutmasi kapali (dogrulama repro'su)
  useEffect(() => {
    if (!selectedId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedId(null);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const yon = e.key === "ArrowDown" ? 1 : -1;
        setSelectedId((curr) => {
          const idx = visible.findIndex((d) => d.id === curr);
          const next = visible[idx + yon];
          return idx !== -1 && next ? next.id : curr;
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, visible]);

  if (isLoading) {
    return <YuklemeIskeleti label="Radar yükleniyor" />;
  }

  // != null: openapi-fetch boş-gövdeli non-ok cevapta error="" (falsy!) verebilir —
  // truthiness kontrolü onu yutup sahte "radar temiz" basardı (doğrulama bulgusu).
  // !data: geçici tek poll hatası eldeki listeyi GİZLEMESİN — veri varken hata
  // sessiz geçilir, polling zaten sürüyor (react-query eski datayı tutar).
  if (error != null && data === undefined) {
    return <HataDurumu baslik="Radar'a ulaşılamıyor" hata={error} />;
  }

  // Filtre değişip seçili tespit görünürden düşerse panel dürüstçe kapanır
  const selected = visible.find((d) => d.id === selectedId) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-base font-semibold">Çakışma radarı</h1>
        <SonGuncelleme dataUpdatedAt={dataUpdatedAt} isFetching={isFetching} />
      </div>

      <PresenceStrip />

      {/* Listenin HEMEN üstünde: uyarı hangi sonucu nitelediği belli olsun */}
      {degraded && <EksikSonucSeridi degraded={degraded} />}

      {detections.length === 0 ? (
        degraded ? (
          // Eksik turda "radar temiz" demek yalan olurdu: değerlendirilebilenlerde
          // çakışma çıkmadı, ama temiz diyecek kanıt elimizde yok (#252).
          <EmptyState
            title="Temiz diyemiyoruz — sonuç eksik"
            description={`Değerlendirilebilen ${degraded.evaluated} çiftte çakışma çıkmadı; ${degraded.judge_unavailable} çift ise hiç değerlendirilemedi. "Radar temiz" demek için yeterli kanıt yok.`}
            eta="Judge erişimi düzelince tur kendiliğinden tazelenir (10 sn'de bir)."
          />
        ) : (
          <EmptyState
            title="Radar temiz — çakışma yok"
            description="İzlenen aktivitede çakışma tespit edilmedi. İki kişinin (ya da AI ajanının) aynı bölgeye kör dokunduğu anlar burada gerekçeli uyarı olarak listelenecek."
            items={[
              "▲ yüksek — aynı dosyada çakışan değişiklik",
              "◆ orta — aynı modülde semantik yakınlık",
              "Judge gerekçesi Türkçe, kanıt listeleriyle",
            ]}
            eta="Canlı tespit: #17 dedektörü + #25 entegrasyonu"
          />
        )
      ) : (
        <>
          <div className="flex gap-1" role="group" aria-label="Severity filtresi">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                aria-pressed={filter === f.key}
                className={`rounded px-2 py-1 text-xs ${
                  filter === f.key
                    ? "bg-muted font-medium"
                    : "text-muted-foreground hover:bg-muted/50"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {visible.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Bu filtrede sonuç yok — {detections.length} tespit diğer seviyelerde.
            </p>
          ) : (
            // Liste + sağdan detay paneli (#156, Pencil MOGXv yerleşimi)
            <div className="flex items-start gap-4">
              <div className="min-w-0 flex-1 space-y-2">
                {anaListe.length > 0 && (
                  <ul aria-label="Tespit listesi" className="space-y-2">
                    {anaListe.map((d) => (
                      <FeedItem
                        key={d.id}
                        detection={d}
                        selected={d.id === selectedId}
                        onSelect={(det) =>
                          setSelectedId(det.id === selectedId ? null : det.id)
                        }
                        bindRef={(el) => {
                          if (el) rowRefs.current.set(d.id, el);
                          else rowRefs.current.delete(d.id);
                        }}
                      />
                    ))}
                  </ul>
                )}

                {/* Hepsi düşükse liste alanı boş kalmasın: sonuç VAR, katlanmış */}
                {anaListe.length === 0 && dusukler.length > 0 && (
                  <p className="text-sm text-muted-foreground">
                    Yüksek ya da orta seviyede tespit yok — {dusukler.length} tespitin
                    hepsi düşük güvende, aşağıda katlı.
                  </p>
                )}

                {/* #158 — katlanan düşük-güven bölümü */}
                {dusukler.length > 0 && (
                  <div className="space-y-2">
                    <button
                      type="button"
                      onClick={() => {
                        // Bölüm kapanırken içindeki seçim de kapanır: gizlenen
                        // satırın detayı açık kalırsa hayalet panel olur
                        if (dusukAcik && selected?.severity === "low") {
                          setSelectedId(null);
                        }
                        setDusukAcik((a) => !a);
                      }}
                      aria-expanded={dusukAcik}
                      aria-controls="dusuk-guven-listesi"
                      className="flex w-full items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-left text-xs text-muted-foreground hover:bg-muted/40"
                    >
                      <span aria-hidden className="font-mono">
                        {dusukAcik ? "▾" : "▸"}
                      </span>
                      <span className="tabular-nums text-foreground">
                        {dusukler.length} düşük-güven tespit
                      </span>
                      <span className="truncate">
                        — {dusukAcik ? "gizlemek için tıkla" : "varsayılan olarak katlı"}
                      </span>
                    </button>

                    {dusukAcik && (
                      <ul
                        id="dusuk-guven-listesi"
                        aria-label="Düşük güvenli tespitler"
                        className="space-y-2"
                      >
                        {dusukler.map((d) => (
                          <FeedItem
                            key={d.id}
                            detection={d}
                            selected={d.id === selectedId}
                            onSelect={(det) =>
                              setSelectedId(det.id === selectedId ? null : det.id)
                            }
                            bindRef={(el) => {
                              if (el) rowRefs.current.set(d.id, el);
                              else rowRefs.current.delete(d.id);
                            }}
                          />
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>

              {selected && (
                <DetailSheet detection={selected} onClose={() => setSelectedId(null)} />
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
