import { EmptyState } from "../components/ui";

export default function BoardPage() {
  return (
    <EmptyState
      title="Kendiliğinden dolan pano"
      description="Kartlar GitHub PR/issue durumundan otomatik oynar — sürükleme yok, bu bir özellik. 5 kolon: backlog → todo → in progress → in review → done."
      eta="Sprint 3 · veri: GET /board"
    />
  );
}
