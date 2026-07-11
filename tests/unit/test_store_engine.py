from unittest.mock import MagicMock


from ensemble.config import Settings
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import Base, PresenceRow, TaskProjectionRow
from ensemble.store.rebuild import rebuild_projection
from ensemble_shared.harness import HarnessPort


def test_sqlite_engine_creation():
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    
    # In-memory veritabanında tabloları oluştur
    Base.metadata.create_all(engine)
    
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        # CRUD testi
        task = TaskProjectionRow(task_id="T-1", title="Test", status="todo")
        session.add(task)
        session.commit()
        
        saved = session.query(TaskProjectionRow).filter_by(task_id="T-1").first()
        assert saved is not None
        assert saved.title == "Test"


def test_rebuild_projection():
    # In-memory DB
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    
    session_factory = get_session_factory(engine)
    session = session_factory()
    
    # Mock HarnessPort
    mock_harness = MagicMock(spec=HarnessPort)
    mock_harness.read_tasks.return_value = [
        {"task_id": "T-1", "title": "A"},
        {"task_id": "T-2", "title": "B"}
    ]
    mock_harness.read_active.return_value = [
        {"handle": "enes", "task": "T-41"},
        {"handle": "esma", "task": "T-24"}
    ]
    
    # Başlangıçta boş
    assert session.query(TaskProjectionRow).count() == 0
    assert session.query(PresenceRow).count() == 0
    
    # Rebuild
    res = rebuild_projection(session, mock_harness)
    
    assert res["tasks"] == 2
    assert res["presence"] == 2
    
    # Doğrulama
    assert session.query(TaskProjectionRow).count() == 2
    assert session.query(PresenceRow).count() == 2
    
    enes = session.query(PresenceRow).filter_by(handle="enes").first()
    assert enes.task == "T-41"
    
    session.close()
