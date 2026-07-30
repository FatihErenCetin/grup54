from unittest.mock import MagicMock


from ensemble.config import Settings
from ensemble.ports import EmbeddingsPort, GitHubPort
from ensemble.store.engine import get_engine, get_session_factory, normalize_database_url
from ensemble.store.models import DEFAULT_REPO_FULL_NAME, Base, PresenceRow, TaskProjectionRow
from ensemble.store.rebuild import rebuild_projection
from ensemble_shared.harness import HarnessPort

_REPO = DEFAULT_REPO_FULL_NAME


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
        task = TaskProjectionRow(task_id="T-1", repo_full_name=_REPO, title="Test", status="todo")
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


def test_rebuild_projection_github_verilince_bos_backfill_vektorleri_temizler():
    """`github` VERİLDİĞİNDE vektör indeksi gerçekten yeniden kurulur — backfill
    boş dönerse indeks de boşalır (eski `stale` vektör kalmaz).

    Bu test eskiden `github` OLMADAN aynı şeyi iddia ediyordu
    (`..._clears_stale_vectors_when_events_empty`) ve tam da #345'in hatasını
    KİLİTLİYORDU: geri doldurulmayacak bir indeksi silmeyi "stale temizliği"
    sanıyordu. Doğru sınır `github`'ın varlığıdır — silme ancak yeniden kurma
    ile birlikte meşrudur.
    """
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

    mock_github = MagicMock(spec=GitHubPort)
    mock_github.fetch_backfill_events.return_value = []

    res = rebuild_projection(
        session,
        mock_harness,
        github=mock_github,
        vector_index=vector_index,
        embeddings=MagicMock(spec=EmbeddingsPort),
    )

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
    session.add(TaskProjectionRow(task_id="T-old", repo_full_name=_REPO, title="Old"))
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
    mock_harness.read_active.return_value = []

    from ensemble.ports import GitHubPort, EmbeddingsPort
    from ensemble.models import NormalizedEvent
    from datetime import datetime, timezone

    mock_github = MagicMock(spec=GitHubPort)
    mock_github.fetch_backfill_events.return_value = [
        NormalizedEvent(id="ev1", type="commit", actor="user", branch="main", ref="123", files=[], ts=datetime.now(timezone.utc))
    ]

    mock_embeddings = MagicMock(spec=EmbeddingsPort)
    mock_embeddings.embed.side_effect = RuntimeError("Embed fail")

    import pytest
    with pytest.raises(RuntimeError):
        rebuild_projection(
            session,
            mock_harness,
            github=mock_github,
            vector_index=vector_index,
            embeddings=mock_embeddings
        )

    # Vector index DB rollback sonrasında dokunulmamış olmalı
    result = vector_index.query([1.0, 0.0], k=10)
    assert len(result) == 1
    assert result[0][0] == "existing-vec", "Vector index DB hatasından etkilenmemeli"

    session.close()


def test_rebuild_writes_vector_index_in_same_db_transaction():
    """Atomiklik (#218): vektör indeksi, DB session'ına ve commit'ten ÖNCE yazılmalı.

    replace_all'a rebuild'in session'ı geçirilirse hosted PgVectorIndex aynı
    transaction'a yazar → DB + vektör tek commit/rollback (atomik). Eski
    'DB commit sonrası ayrı transaction' akışına dönülürse bu test kırılır.
    """
    from datetime import datetime, timezone

    from ensemble.models import NormalizedEvent
    from ensemble.ports import GitHubPort

    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session = get_session_factory(engine)()

    mock_harness = MagicMock(spec=HarnessPort)
    mock_harness.read_tasks.return_value = []
    mock_harness.read_active.return_value = []

    mock_github = MagicMock(spec=GitHubPort)
    mock_github.fetch_backfill_events.return_value = [
        NormalizedEvent(
            id="ev1", type="commit", actor="u", branch="main", ref="1", files=[],
            ts=datetime.now(timezone.utc),
        )
    ]
    mock_embeddings = MagicMock(spec=EmbeddingsPort)
    mock_embeddings.embed.return_value = [[1.0, 0.0]]

    spy_index = MagicMock()

    rebuild_projection(
        session,
        mock_harness,
        github=mock_github,
        vector_index=spy_index,
        embeddings=mock_embeddings,
    )

    spy_index.replace_all.assert_called_once()
    _, kwargs = spy_index.replace_all.call_args
    assert kwargs.get("session") is session, "replace_all rebuild session'ı ile çağrılmalı (aynı transaction)"

    session.close()


def test_rebuild_stages_vectors_into_index():
    """#191 kabul kriteri: seed sonrası semantik sorgu boş DEĞİL — en az 1 gerçek sonuç."""
    from ensemble.engine.embeddings import HashEmbeddings
    from ensemble.integrations.github.fake import FakeGitHubAdapter
    from ensemble.store.vector_store import LocalVectorIndex

    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session = get_session_factory(engine)()

    mock_harness = MagicMock(spec=HarnessPort)
    mock_harness.read_tasks.return_value = []
    mock_harness.read_active.return_value = []

    embeddings = HashEmbeddings()
    github = FakeGitHubAdapter()  # deterministik default eventler (commit/pr/issue)
    vector_index = LocalVectorIndex()

    res = rebuild_projection(
        session,
        mock_harness,
        github=github,
        vector_index=vector_index,
        embeddings=embeddings,
    )

    assert res["events"] >= 1, "seed en az bir event yazmalı"
    query_vec = embeddings.embed(["commit by esma"], task_type="RETRIEVAL_QUERY")[0]
    hits = vector_index.query(query_vec, k=5)
    assert len(hits) >= 1, "seed sonrası semantik sorgu boş dönmemeli (#191 kanıtı)"

    session.close()


def test_rebuild_main_entrypoint_blocks_fake_github_port():
    import os
    import subprocess
    import sys
    import tempfile
    from datetime import datetime, timezone
    
    from ensemble.config import Settings
    from ensemble.store.engine import get_engine, get_session_factory
    from ensemble.store.models import Base, EventRow
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
        
    db_url = f"sqlite:///{db_path}"
    settings = Settings(DATABASE_URL=db_url)
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        session.add(
            EventRow(
                id="existing",
                repo_full_name=_REPO,
                type="test",
                actor="user",
                branch="b",
                ts=datetime.now(timezone.utc),
                ref="abc",
            )
        )
        session.commit()
    
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["ENSEMBLE_ALLOW_FAKE_SEED"] = "0"
    
    # Set fake github port via missing settings (no GITHUB_APP_ID etc.)
    if "GITHUB_APP_ID" in env:
        del env["GITHUB_APP_ID"]
    
    # Add project root to PYTHONPATH so `ensemble` module can be found
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "backend"))
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{project_root}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = project_root

    result = subprocess.run(
        [sys.executable, "-m", "ensemble.store.rebuild"],
        env=env,
        capture_output=True,
        text=True
    )
    
    assert result.returncode != 0
    assert "rebuild reddedildi: gercek GitHub App yok" in result.stderr or "rebuild reddedildi: gercek GitHub App yok" in result.stdout
    
    with session_factory() as session:
        events = session.query(EventRow).all()
        assert len(events) == 1
        assert events[0].id == "existing"
        
    engine.dispose()
    try:
        os.unlink(db_path)
    except PermissionError:
        pass
