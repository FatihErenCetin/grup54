from datetime import datetime

from ensemble.models import BoardCard, NormalizedEvent
from ensemble.store.models import EventRow, PresenceRow, TaskProjectionRow, TaskStatusEventRow


def test_event_row_roundtrip():
    event = NormalizedEvent(
        id="e1",
        type="commit",
        actor="esma6",
        branch="main",
        files=["test.py"],
        ts=datetime(2026, 7, 10, 15, 0),
        ref="abc",
    )
    
    row = EventRow.from_domain(event)
    assert row.id == "e1"
    assert row.actor == "esma6"
    assert row.files == ["test.py"]
    
    restored = row.to_domain()
    assert restored == event


def test_task_projection_from_harness():
    data = {
        "task_id": "T-41",
        "title": "Projeksiyon deposu",
        "status": "in_progress",
        "assignee": "EnesErdemT",
        "ref": "#41"
    }
    row = TaskProjectionRow.from_harness(data)
    assert row.task_id == "T-41"
    assert row.title == "Projeksiyon deposu"
    assert row.status == "in_progress"

    card = row.to_board_card()
    assert card == BoardCard(
        task_id="T-41",
        title="Projeksiyon deposu",
        status="in_progress",
        assignee="EnesErdemT",
        ref="#41",
    )


def test_task_projection_from_harness_seed_status_ayri_tutulur():
    # from_harness() satırın hem status'ünü (henüz katlanmamış tohum) hem de
    # seed_status'ünü (fold'un başlangıç noktası, D-55 İş 2) AYNI tohum
    # değeriyle kurar — rebuild_projection() sonradan yalnız status'ü katlar,
    # seed_status kalıcı olarak tohumu taşır (bkz. test_rebuild.py
    # test_seed_degisse_de_fold_sonucu_korunur).
    data = {"task_id": "T-158", "title": "Health zinciri", "status": "todo"}
    row = TaskProjectionRow.from_harness(data)
    assert row.status == "todo"
    assert row.seed_status == "todo"
    assert row.last_transition_at is None
    assert row.last_event_id is None


def test_task_status_event_row_alanlari():
    # task_status_events kalıcı durum günlüğü satırı — status ÇÖZÜLMÜŞ hedef
    # durumdur (ham GitHub event tipi değil), reason insan-okur debug bilgisi.
    # resets burada AÇIKÇA verilir (Python-side default=False yalnızca
    # flush/insert anında uygulanır, çıplak nesne örneğinde değil — default
    # davranışı tests/unit/test_rebuild.py'de gerçek bir session üzerinden
    # dolaylı olarak zaten doğrulanıyor).
    row = TaskStatusEventRow(
        source_event_id="issue-258-closed",
        task_id="T-158",
        status="done",
        ts=datetime(2026, 7, 25, 12, 0),
        reason="issue_closed",
        resets=True,
    )
    assert row.source_event_id == "issue-258-closed"
    assert row.task_id == "T-158"
    assert row.status == "done"
    assert row.reason == "issue_closed"
    assert row.resets is True


def test_presence_row_from_harness():
    # active.schema.json alan adlari: task_id, updated_at (task/since DEGIL) —
    # updated_at semada string zorunlu (FileHarnessPort.read_active() ISO
    # datetime'i string'e coerce eder, bkz. test_harness.py).
    data = {
        "handle": "EnesErdemT",
        "task_id": "T-41",
        "module": "store",
        "intent": "migrations",
        "branch": "T-41-projeksiyon-deposu",
        "updated_at": "2026-07-11T10:00:00",
    }
    row = PresenceRow.from_harness(data)
    assert row.handle == "EnesErdemT"
    assert row.task == "T-41"
    assert row.module == "store"
    assert row.since == datetime(2026, 7, 11, 10, 0)
