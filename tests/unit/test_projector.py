from datetime import datetime
from unittest.mock import MagicMock


from ensemble.config import Settings
from ensemble.engine.projector import Projector
from ensemble.models import NormalizedEvent
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import Base, EventRow, PresenceRow, TaskProjectionRow
from ensemble_shared.harness import HarnessPort


def test_project_events():
    # Setup in-memory db
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()

    # Create initial tasks via direct DB insert (mocking rebuild_projection)
    task = TaskProjectionRow(task_id="T-47", title="Projeksiyon yazıcı", status="todo")
    session.add(task)
    session.commit()

    # Mock harness
    mock_harness = MagicMock(spec=HarnessPort)
    mock_harness.read_active.return_value = [
        {"handle": "enes", "task": "T-47", "since": datetime(2026, 7, 11, 10, 0)}
    ]

    # Create dummy events
    commit_event = NormalizedEvent(
        id="c1",
        type="commit",
        actor="enes",
        branch="T-47-yeni-ozellik",
        files=["test.py"],
        ts=datetime.now(),
        ref="sha123"
    )

    pr_event = NormalizedEvent(
        id="pr1",
        type="pr",
        actor="esma",
        branch="T-47-yeni-ozellik",
        files=[],
        ts=datetime.now(),
        ref="47"
    )

    projector = Projector(session, mock_harness)
    
    # 1. Project commit event -> should turn T-47 to 'in_progress'
    res1 = projector.project_events([commit_event])
    assert res1["events_processed"] == 1
    
    t1 = session.query(TaskProjectionRow).filter_by(task_id="T-47").first()
    assert t1.status == "in_progress"
    
    # 2. Project pr event -> should turn T-47 to 'in_review'
    res2 = projector.project_events([pr_event])
    assert res2["events_processed"] == 1
    
    t2 = session.query(TaskProjectionRow).filter_by(task_id="T-47").first()
    assert t2.status == "in_review"
    
    # Check EventRows and PresenceRows
    assert session.query(EventRow).count() == 2
    assert session.query(PresenceRow).count() == 1
    
    p = session.query(PresenceRow).first()
    assert p.handle == "enes"
    assert p.task == "T-47"

    session.close()
