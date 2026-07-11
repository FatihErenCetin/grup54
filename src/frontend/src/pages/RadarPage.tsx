import { EmptyState } from "../components/ui";

export default function RadarPage() {
  return (
    <EmptyState
      title="Çakışma radarı bağlantı bekliyor"
      description="Backend'e bağlanınca iki kişinin (ya da AI ajanının) aynı modüle dokunduğu anlar burada gerekçeli uyarı olarak listelenecek."
      items={[
        "▲ yüksek — aynı dosyada çakışan değişiklik",
        "◆ orta — aynı modülde semantik yakınlık",
        "Judge gerekçesi Türkçe, kanıt linkleriyle",
      ]}
      eta="Sprint 2 · #21 (sayfa) + #25 (canlı veri)"
    />
  );
}
