import { EmptyState } from "../components/ui";

export default function ScopePage() {
  return (
    <EmptyState
      title="Kapsam bekçisi"
      description="Dondurulmuş sprint kapsamı solda; açık PR'ların kapsam kararları (in_scope / drift / non_goal_violation) sağda, kanıt alıntılarıyla."
      eta="Sprint 3 · veri: GET /scope/check"
    />
  );
}
