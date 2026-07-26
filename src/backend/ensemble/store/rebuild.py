"""Projeksiyon yeniden kurma — .harness/ kanonik kaynak → DB cache (#41).

D-55 (İş 2) öncesi: rebuild_projection() `task_projection`'ı SİLİP yalnızca
.harness'ten yeniden kuruyordu — webhook'un yazdığı GERÇEK GitHub durumu ilk
rebuild'de KAYBOLUYORDU (bulunan çelişki: engine/projector.py'nin yazdığı
`status`, store/rebuild.py'nin sildiği ilk şeydi).

Şimdi: kimlik/içerik (.harness) TOHUM, durum GERÇEK GitHub olayı — ikisi
`task_status_events` (append-only, kalıcı) üzerinden KATLANIR (fold). Bu
yüzden rebuild_projection() artık "sil + tohumdan kur" değil, "sil + tohumdan
kur + geçişleri yeniden oyna" — yani rebuild İDEMPOTENT'tir ve canlı yolla
AYNI sonucu verir (DB tamamen silinse bile `.harness` tohumu + GitHub
backfill'i ile yeniden kurulabilir; "DB kanonik değil" iddiası kanıtlı kalır).
"""

from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from ensemble.store.models import PresenceRow, TaskProjectionRow, TaskStatusEventRow
from ensemble_shared.harness import HarnessPort


def append_status_events(session: Session, events: Iterable[TaskStatusEventRow]) -> int:
    """`task_status_events`'e append-only ekleme.

    Aynı (`source_event_id`, `task_id`) çifti ikinci kez gelirse (GitHub'ın
    aynı webhook'u yeniden teslim etmesi — retry) satır ÇOĞALTILMAZ, sessizce
    atlanır. Fail-open ÜRETMEZ: atlanan satır sayılır (dönüş değeri yalnızca
    GERÇEKTEN eklenen satır sayısıdır), kaybolmaz — zaten DB'de var.

    Args:
        session: aktif SQLAlchemy oturumu (caller commit eder).
        events: eklenecek TaskStatusEventRow nesneleri (henüz session'a
            eklenmemiş / flush edilmemiş olabilir).

    Returns:
        Gerçekten eklenen (yeni) satır sayısı.
    """
    inserted = 0
    for event in events:
        existing = session.get(TaskStatusEventRow, (event.source_event_id, event.task_id))
        if existing is not None:
            continue
        session.add(event)
        session.flush()
        inserted += 1
    return inserted


def fold_status(
    seed: str, rows: Iterable[TaskStatusEventRow]
) -> tuple[str, datetime | None, str | None]:
    """Tohum + biriken geçişleri deterministik olarak katla (fold).

    `rows`, (`ts`, `source_event_id`) sırasına göre sıralanır — KRONOLOJİK
    sıra esastır, satırların DB'ye YAZILMA (insertion) sırası DEĞİL. Böylece
    ağ gecikmesiyle GEÇ gelen ama ts'i ESKİ olan bir olay, daha sonra gelmiş
    ts'i YENİ satırların sonucunu BOZMAZ (bkz.
    tests/unit/test_rebuild.py test_gec_gelen_eski_olay_durumu_bozmaz).

    Her satırın `status`'ü zaten ÇÖZÜLMÜŞ hedef durumdur (engine/status_rules.py
    sorumluluğu — İş 1); burada yalnızca sıralı katlama yapılır, ham GitHub
    event tipinden yeniden türetme YOKTUR.

    Args:
        seed: `.harness/tasks/T-<id>.md` dosyasındaki tohum `status`.
        rows: bu task_id için birikmiş TaskStatusEventRow satırları.

    Returns:
        (folded_status, son_geçiş_ts'i veya None, son_geçiş_event_id'si veya None).
        Hiç satır yoksa (folded_status == seed, None, None) döner.
    """
    ordered = sorted(rows, key=lambda row: (row.ts, row.source_event_id))

    current = seed
    last_ts: datetime | None = None
    last_event_id: str | None = None
    for row in ordered:
        current = row.status
        last_ts = row.ts
        last_event_id = row.source_event_id

    return current, last_ts, last_event_id


def rebuild_projection(session: Session, harness: HarnessPort) -> dict[str, int]:
    """Harness (tohum) + birikmiş task_status_events'ten projeksiyonu yeniden kur.

    Sıra ÖNEMLİ: ÖNCE tohumdan (`.harness` `status`) kurulur, SONRA
    `task_status_events` (`ts`, `source_event_id`) sırasıyla katlanır (fold).
    `task_status_events` bu fonksiyon tarafından SİLİNMEZ (append-only kalıcı
    günlük) — yalnızca `task_projection` ve `presence` yeniden inşa edilir; bu
    yüzden art arda iki çağrı BİT-BİT AYNI sonucu üretir (idempotent).

    .harness'te karşılığı olmayan bir task_id için geçiş bulunursa: satır
    `task_status_events`'te KALIR (kaybolmaz) ama `task_projection`'a yeni kart
    UYDURULMAZ — bu satırlar `orphan_transitions` olarak sayılır (fail-open
    üretmez, sessizce yutulmaz).

    Returns:
        {"tasks": N, "presence": M, "transitions_applied": K,
         "orphan_transitions": O}
    """
    # --- tasks: tohumdan kur ---
    session.query(TaskProjectionRow).delete()

    tasks = harness.read_tasks()
    task_rows: dict[str, TaskProjectionRow] = {}
    for task_data in tasks:
        row = TaskProjectionRow.from_harness(task_data)
        task_rows[row.task_id] = row
    session.add_all(task_rows.values())
    session.flush()

    # --- presence (active/) ---
    session.query(PresenceRow).delete()

    actives = harness.read_active()
    presence_rows = [PresenceRow.from_harness(a) for a in actives]
    session.add_all(presence_rows)

    # --- transitions: kalıcı günlüğü (ts, source_event_id) sırasıyla katla ---
    by_task: dict[str, list[TaskStatusEventRow]] = {}
    for event_row in session.query(TaskStatusEventRow).all():
        by_task.setdefault(event_row.task_id, []).append(event_row)

    transitions_applied = 0
    orphan_transitions = 0
    for task_id, rows in by_task.items():
        transitions_applied += len(rows)
        task_row = task_rows.get(task_id)
        if task_row is None:
            # .harness'te olmayan task_id — kaybolmaz (satır task_status_events'te
            # kalır), ama task_projection'a UYDURULMAZ.
            orphan_transitions += len(rows)
            continue
        folded_status, last_ts, last_event_id = fold_status(task_row.seed_status, rows)
        task_row.status = folded_status
        task_row.last_transition_at = last_ts
        task_row.last_event_id = last_event_id

    session.commit()

    return {
        "tasks": len(task_rows),
        "presence": len(presence_rows),
        "transitions_applied": transitions_applied,
        "orphan_transitions": orphan_transitions,
    }
