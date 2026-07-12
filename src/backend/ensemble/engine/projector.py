"""Projeksiyon yazıcı (Projector) — eventler ve harness verisinden DB durumunu günceller (#47)."""

from sqlalchemy.orm import Session

from ensemble.integrations.github.normalize import extract_task_id
from ensemble.models import NormalizedEvent
from ensemble.store.models import EventRow, PresenceRow, TaskProjectionRow
from ensemble_shared.harness import HarnessPort


class Projector:
    """GitHub eventleri ve .harness verisini okuyarak DB projeksiyonunu günceller."""

    def __init__(self, session: Session, harness: HarnessPort) -> None:
        self.session = session
        self.harness = harness

    def project_events(self, events: list[NormalizedEvent]) -> dict[str, int]:
        """Yeni gelen NormalizedEvent listesini işler ve projeksiyonları günceller.
        
        - Tüm eventler EventRow olarak DB'ye yazılır (audit).
        - İlgili eventlerin task_id'leri bulunursa TaskProjectionRow durumu güncellenir.
        - .harness/active/ güncel durumu PresenceRow tablosuna yansıtılır.
        """
        # 1. Eventleri audit log olarak ekle
        event_rows = []
        for event in events:
            # Idempotency: Eğer DB'de varsa ekleme (veya Upsert yap)
            # SQLite upsert için merge kullanıyoruz.
            row = EventRow.from_domain(event)
            self.session.merge(row)
            event_rows.append(row)

        # 2. Eventlerden Task statülerini çıkar ve güncelle
        # MVP kuralı: commit -> in_progress, pr -> in_review
        task_updates = {}
        for event in events:
            task_id_num = extract_task_id(branch=event.branch)
            if task_id_num:
                task_id = f"T-{task_id_num}"
                if event.type == "commit":
                    task_updates[task_id] = "in_progress"
                elif event.type == "pr":
                    task_updates[task_id] = "in_review"

        for task_id, status in task_updates.items():
            task_row = self.session.query(TaskProjectionRow).filter_by(task_id=task_id).first()
            if task_row:
                # Sadece ileri yönlü basit geçişler
                # Eğer mevcut durum done değilse güncelle
                if task_row.status != "done":
                    task_row.status = status

        # 3. Presence (active) tablosunu senkronize et
        self.session.query(PresenceRow).delete()
        actives = self.harness.read_active()
        presence_rows = [PresenceRow.from_harness(a) for a in actives]
        self.session.add_all(presence_rows)

        self.session.commit()

        return {
            "events_processed": len(events),
            "tasks_updated": len(task_updates),
            "presence_synced": len(presence_rows),
        }
