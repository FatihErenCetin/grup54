"""Projeksiyon yeniden kurma — .harness/ kanonik kaynak → DB cache (#41).

.harness/ + GitHub her zaman kazanır (AGENTS.md mimari ilkeleri).
DB bozulursa veya çelişirse: rebuild_projection() çağrılır → tablolar
truncate + insert ile yeniden doldurulur. make rebuild komutuyla çağrılır.
"""

from sqlalchemy.orm import Session

from ensemble.ports import EmbeddingsPort, GitHubPort, VectorIndexPort
from ensemble.store.models import EventRow, PresenceRow, TaskProjectionRow
from ensemble_shared.harness import HarnessPort


def rebuild_projection(
    session: Session,
    harness: HarnessPort,
    github: GitHubPort | None = None,
    backfill_limit: int = 50,
    vector_index: VectorIndexPort | None = None,
    embeddings: EmbeddingsPort | None = None,
) -> dict[str, int]:
    """Harness'tan ve GitHub'dan okunan veriyle projeksiyon tablolarını ve vektör indeksini yeniden kur.

    Returns:
        {"tasks": N, "presence": M, "events": E} — eklenen satır sayıları.
    """
    # --- tasks ---
    session.query(TaskProjectionRow).delete()

    tasks = harness.read_tasks()
    task_rows = [TaskProjectionRow.from_harness(t) for t in tasks]
    session.add_all(task_rows)

    # --- presence (active/) ---
    session.query(PresenceRow).delete()

    actives = harness.read_active()
    presence_rows = [PresenceRow.from_harness(a) for a in actives]
    session.add_all(presence_rows)

    # --- events (backfill & vector index) ---
    session.query(EventRow).delete()

    if vector_index is not None:
        vector_index.clear()

    event_rows: list[EventRow] = []
    if github is not None:
        events = github.fetch_backfill_events(limit_per_type=backfill_limit)
        event_rows = [EventRow.from_domain(e) for e in events]
        session.add_all(event_rows)

        if vector_index is not None and embeddings is not None and events:
            texts = [
                f"Event: {e.type} by {e.actor} on {e.branch or 'none'} at {e.ref}. Files: {', '.join(e.files)}"
                for e in events
            ]
            vectors = embeddings.embed(texts, task_type="RETRIEVAL_DOCUMENT")
            for event, vec in zip(events, vectors, strict=True):
                meta = {
                    "type": event.type,
                    "actor": event.actor,
                    "branch": event.branch,
                    "files": event.files,
                    "ts": event.ts.isoformat(),
                    "ref": event.ref,
                }
                vector_index.upsert(event.id, vec, meta)

    session.commit()

    return {"tasks": len(task_rows), "presence": len(presence_rows), "events": len(event_rows)}
