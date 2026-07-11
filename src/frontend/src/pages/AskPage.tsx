import { EmptyState } from "../components/ui";

export default function AskPage() {
  return (
    <EmptyState
      title="Projeye sor"
      description={`"Ben yokken ne değişti?" · "Auth'a kim dokundu?" — doğal dille sor, kaynak alıntılı cevap al.`}
      eta="Sprint 3 · veri: GET /query"
    />
  );
}
