from unittest.mock import MagicMock


from ensemble.config import Settings
from ensemble.ports import EmbeddingsPort, GitHubPort
from ensemble.store.engine import get_engine, get_session_factory, normalize_database_url
from ensemble.store.models import Base, PresenceRow, TaskProjectionRow
from ensemble.store.rebuild import rebuild_projection
from ensemble_shared.harness import HarnessPort


def test_normalize_database_url():
    assert (
        normalize_database_url("postgres://user:pass@localhost:5432/db")
        == "postgresql+psycopg://user:pass@localhost:5432/db"
    )
    assert (
        normalize_database_url("postgresql://user:pass@localhost:5432/db")
        == "postgresql+psycopg://user:pass@localhost:5432/db"
    )
    assert (
        normalize_database_url("postgresql+psycopg://user:pass@localhost:5432/db")
        == "postgresql+psycopg://user:pass@localhost:5432/db"
    )
    assert normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_postgres_engine_creation_url_normalization():
    settings = Settings(DATABASE_URL="postgres://user:pass@localhost:5432/db")
    engine = get_engine(settings)
    assert engine.url.drivername == "postgresql+psycopg"


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
        {"handle": "enes", "task_id": "T-41"},
        {"handle": "esma", "task_id": "T-24"}
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


def test_rebuild_projection_clears_stale_vectors_when_events_empty():
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)

    session_factory = get_session_factory(engine)
    session = session_factory()

    mock_harness = MagicMock(spec=HarnessPort)
    mock_harness.read_tasks.return_value = []
    mock_harness.read_active.return_value = []

    from ensemble.store.vector_store import LocalVectorIndex
    vector_index = LocalVectorIndex()
    vector_index.upsert("stale-1", [1.0, 0.0], {"type": "old"})

    res = rebuild_projection(session, mock_harness, vector_index=vector_index)

    assert res["events"] == 0
    assert vector_index.query([1.0, 0.0], k=10) == []
    session.close()


def test_rebuild_projection_with_github_events_and_vector_index():
    from datetime import datetime, timezone
    from ensemble.models import NormalizedEvent
    from ensemble.ports import GitHubPort
    from ensemble.store.models import EventRow
    from ensemble.store.vector_store import LocalVectorIndex

    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)

    session_factory = get_session_factory(engine)
    session = session_factory()

    mock_harness = MagicMock(spec=HarnessPort)
    mock_harness.read_tasks.return_value = []
    mock_harness.read_active.return_value = []

    event = NormalizedEvent(
        id="evt-100",
        type="commit",
        actor="enes",
        branch="main",
        files=["a.py"],
        ts=datetime.now(timezone.utc),
        ref="ref-1",
    )
    mock_github = MagicMock(spec=GitHubPort)
    mock_github.fetch_backfill_events.return_value = [event]

    mock_embeddings = MagicMock(spec=EmbeddingsPort)
    mock_embeddings.embed.return_value = [[1.0, 0.0]]

    vector_index = LocalVectorIndex()
    vector_index.upsert("stale-1", [0.0, 1.0], {"type": "stale"})

    res = rebuild_projection(
        session,
        mock_harness,
        github=mock_github,
        vector_index=vector_index,
        embeddings=mock_embeddings,
    )

    assert res["events"] == 1
    assert session.query(EventRow).count() == 1
    query_res = vector_index.query([1.0, 0.0], k=10)
    assert [id for id, _ in query_res] == ["evt-100"]

    session.close()


def test_rebuild_projection_with_github_fails_if_deps_missing():
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()

    mock_harness = MagicMock(spec=HarnessPort)
    mock_github = MagicMock(spec=GitHubPort)

    import pytest
    from ensemble.store.vector_store import LocalVectorIndex

    with pytest.raises(ValueError, match="requires both vector_index and embeddings"):
        rebuild_projection(
            session,
            mock_harness,
            github=mock_github,
            vector_index=None,
            embeddings=MagicMock(spec=EmbeddingsPort)
        )

    with pytest.raises(ValueError, match="requires both vector_index and embeddings"):
        rebuild_projection(
            session,
            mock_harness,
            github=mock_github,
            vector_index=LocalVectorIndex(),
            embeddings=None
        )

    session.close()


def test_rebuild_projection_rolls_back_on_error():
    from ensemble.store.models import TaskProjectionRow
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()

    # Önceden veri ekle
    session.add(TaskProjectionRow(task_id="T-old", title="Old"))
    session.commit()

    mock_harness = MagicMock(spec=HarnessPort)
    # Tasks başarıyla okunacak, active okunurken hata verecek (hata fırlatan Exception)
    mock_harness.read_tasks.return_value = [{"task_id": "T-new", "title": "New"}]
    mock_harness.read_active.side_effect = RuntimeError("Harness read error")

    import pytest
    with pytest.raises(RuntimeError, match="Harness read error"):
        rebuild_projection(session, mock_harness)

    # Rollback yapıldığı için DB state ilk baştaki gibi kalmalı
    tasks = session.query(TaskProjectionRow).all()
    assert len(tasks) == 1
    assert tasks[0].task_id == "T-old"

    session.close()


def test_vector_index_untouched_on_db_rollback():
    """DB hatasında vector index temizlenmemeli — rollback tutarsızlığı fix'i (#218)."""
    from ensemble.store.vector_store import LocalVectorIndex

    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()

    # Önceden dolu vector index
    vector_index = LocalVectorIndex()
    vector_index.upsert("existing-vec", [1.0, 0.0], {"type": "before"})

    mock_harness = MagicMock(spec=HarnessPort)
    mock_harness.read_tasks.return_value = []
    # read_active hata verecek — DB rollback tetiklenir
    mock_harness.read_active.side_effect = RuntimeError("Harness fail")

    import pytest
    with pytest.raises(RuntimeError):
        rebuild_projection(session, mock_harness, vector_index=vector_index)

    # Vector index DB rollback sonrasında dokunulmamış olmalı
    result = vector_index.query([1.0, 0.0], k=10)
    assert len(result) == 1
    assert result[0][0] == "existing-vec", "Vector index DB hatasından etkilenmemeli"

    session.close()

