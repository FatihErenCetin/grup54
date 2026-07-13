import { useState } from "react";
import { FeedItem } from "../components/FeedItem";
import { PresenceStrip } from "../components/PresenceStrip";
import { EmptyState, SonGuncelleme } from "../components/ui";
import { useRadar } from "../lib/useRadar";

type SeverityFilter = "hepsi" | "high" | "med" | "low";

const FILTERS: { key: SeverityFilter; label: string }[] = [
  { key: "hepsi", label: "Hepsi" },
  { key: "high", label: "▲ yüksek" },
  { key: "med", label: "◆ orta" },
  { key: "low", label: "● düşük" },
];

/* Radar sayfası (#21) — "AI-grading görünür yüz": severity + confidence +
   TR judge-rationale jüriye burada görünür.
   Gate'li (eksik DEĞİL, bilinçli — PR gövdesi + tasarım paketi "cila tuzağı"):
   Aktif/Drift/Çözüldü sekmeleri (status S3, Ek B1) · aksiyon butonları
   (yazma ucu B6 ertelemesi) · yaş (first_seen_at S3) · "N yeni" pili (B2) ·
   locks gösterimi (.harness/locks henüz yok).
   Bilinçli tasarım sapması: paketteki boş durum "kurulum checklist'i"ydi —
   backend bağlıyken doğru boş durum "radar temiz"dir; checklist onboarding'e
   (S3 sihirbaz) ait. */
export default function RadarPage() {
  const { data, isLoading, isFetching, dataUpdatedAt, error } = useRadar();
  const [filter, setFilter] = useState<SeverityFilter>("hepsi");

  if (isLoading) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Radar yükleniyor">
        <div className="h-10 animate-pulse rounded-lg bg-muted" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-14 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
    );
  }

  // != null: openapi-fetch boş-gövdeli non-ok cevapta error="" (falsy!) verebilir —
  // truthiness kontrolü onu yutup sahte "radar temiz" basardı (doğrulama bulgusu).
  // !data: geçici tek poll hatası eldeki listeyi GİZLEMESİN — veri varken hata
  // sessiz geçilir, polling zaten sürüyor (react-query eski datayı tutar).
  if (error != null && data === undefined) {
    return (
      <EmptyState
        title="Radar'a ulaşılamıyor"
        description="Backend cevap vermedi — bağlantıyı ve VITE_API_BASE_URL'i kontrol et. Polling sürüyor; düzelince kendiliğinden gelir."
      />
    );
  }

  const detections = data?.detections ?? [];
  const visible =
    filter === "hepsi" ? detections : detections.filter((d) => d.severity === filter);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-base font-semibold">Çakışma radarı</h1>
        <SonGuncelleme dataUpdatedAt={dataUpdatedAt} isFetching={isFetching} />
      </div>

      <PresenceStrip />

      {detections.length === 0 ? (
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
            <ul className="space-y-2">
              {visible.map((d) => (
                <FeedItem key={d.id} detection={d} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
