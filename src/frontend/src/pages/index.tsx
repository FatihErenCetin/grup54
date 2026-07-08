import { EmptyState } from "../components/ui";

/* Sayfa stub'ları (#19) — karar 1-C: sidebar tam, her sayfa TASARLANMIŞ
   boş-durumla açılır (ölü link yok). Dolduracak issue parantezde. */

export function RadarPage() {
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

export function BoardPage() {
  return (
    <EmptyState
      title="Kendiliğinden dolan pano"
      description="Kartlar GitHub PR/issue durumundan otomatik oynar — sürükleme yok, bu bir özellik. 5 kolon: backlog → todo → in progress → in review → done."
      eta="Sprint 3 · veri: GET /board"
    />
  );
}

export function ScopePage() {
  return (
    <EmptyState
      title="Kapsam bekçisi"
      description="Dondurulmuş sprint kapsamı solda; açık PR'ların kapsam kararları (in_scope / drift / non_goal_violation) sağda, kanıt alıntılarıyla."
      eta="Sprint 3 · veri: GET /scope/check"
    />
  );
}

export function GraphPage() {
  return (
    <EmptyState
      title="Dokunma grafı"
      description="Kim şu an neye dokunuyor — aktör×modül haritası. Isı matrisi + güç-yönlü graf görünümleri."
      eta="S2 çekme adayı · #104 (veri) + #105 (bu sayfa)"
    />
  );
}

export function ActivityPage() {
  return (
    <EmptyState
      title="Olay akışı"
      description="Kişi bazlı günlük özet — 'kendiliğinden daily'. Kim dün ne yaptı, bugün neye başladı."
      eta="Sprint 3 · veri: GET /events"
    />
  );
}

export function AskPage() {
  return (
    <EmptyState
      title="Projeye sor"
      description={`"Ben yokken ne değişti?" · "Auth'a kim dokundu?" — doğal dille sor, kaynak alıntılı cevap al.`}
      eta="Sprint 3 · veri: GET /query"
    />
  );
}
