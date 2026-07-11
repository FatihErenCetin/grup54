from datetime import datetime

from ensemble.models import BoardCard, NormalizedEvent
from ensemble.store.models import EventRow, PresenceRow, TaskProjectionRow


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
