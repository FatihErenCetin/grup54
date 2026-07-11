import { EmptyState } from "../components/ui";

export default function ActivityPage() {
  return (
    <EmptyState
      title="Olay akışı"
      description="Kişi bazlı günlük özet — 'kendiliğinden daily'. Kim dün ne yaptı, bugün neye başladı."
      eta="Sprint 3 · veri: GET /events"
    />
  );
}
