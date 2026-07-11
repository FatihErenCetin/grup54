"""Projeksiyon yeniden kurma — .harness/ kanonik kaynak → DB cache (#41).

.harness/ + GitHub her zaman kazanır (AGENTS.md mimari ilkeleri).
DB bozulursa veya çelişirse: rebuild_projection() çağrılır → tablolar
truncate + insert ile yeniden doldurulur. make rebuild komutuyla çağrılır.
"""

from sqlalchemy.orm import Session

from ensemble.store.models import PresenceRow, TaskProjectionRow
from ensemble_shared.harness import HarnessPort


def rebuild_projection(session: Session, harness: HarnessPort) -> dict[str, int]:
    """Harness'tan okunan veriyle projeksiyon tablolarını yeniden kur.

    Returns:
        {"tasks": N, "presence": M} — eklenen satır sayıları.
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

    session.commit()

    return {"tasks": len(task_rows), "presence": len(presence_rows)}
