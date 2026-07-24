"""SQL-Şekil ve Gerçek DB Smoke Test Suite for Postgres + pgvector provision (#182)."""

import os
from types import SimpleNamespace
import pytest

from ensemble.config import Settings
from ensemble.store.vector_store import PgVectorIndex, build_vector_index

try:
    from ensemble.store.engine import get_engine, normalize_database_url
except ImportError:
    from ensemble.store.engine import get_engine  # type: ignore

    def normalize_database_url(url: str) -> str:
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


def test_hosted_pgvector_config_and_dsn_sql_shape_smoke():
    raw_url = "postgresql://ensemble:secret_pass@grup54-db.internal:5432/ensemble"
    normalized = normalize_database_url(raw_url)
    assert (
        normalized
        == "postgresql+psycopg://ensemble:secret_pass@grup54-db.internal:5432/ensemble"
    )

    settings = Settings(ENSEMBLE_MODE="hosted", DATABASE_URL=raw_url)
    engine = get_engine(settings)
    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.host == "grup54-db.internal"
    assert engine.url.database == "ensemble"


def test_pgvector_ddl_and_extension_sql_shape_smoke():
    sessions = _FakeSessionFactory()
    index = PgVectorIndex(sessions, dimensions=768, table_name="vector_index")

    index.create_schema()
    statements = [call.sql for call in sessions.calls]
    assert any("CREATE TABLE IF NOT EXISTS vector_index" in stmt for stmt in statements)
    assert any("embedding vector(768)" in stmt for stmt in statements)


def test_pgvector_index_hosted_query_contract_sql_shape_smoke():
    settings = Settings(ENSEMBLE_MODE="hosted", GEMINI_EMBEDDING_DIMENSIONS=3)
    sessions = _FakeSessionFactory()
    index = build_vector_index(settings, session_factory=sessions)

    assert isinstance(index, PgVectorIndex)
    index.upsert("doc-1", [1.0, 0.0, 0.0], {"type": "event"})
    results = index.query([1.0, 0.0, 0.0], k=1)

    statements = [call.sql for call in sessions.calls]

    assert any("CAST(:embedding AS vector)" in stmt for stmt in statements)
    assert any("ORDER BY embedding <=> CAST(:embedding AS vector)" in stmt for stmt in statements)
    assert results == [("near", 0.99)]


@pytest.mark.skipif(
    not os.getenv("ENSEMBLE_TEST_PGVECTOR_URL"),
    reason="ENSEMBLE_TEST_PGVECTOR_URL not configured for live pgvector integration test",
)
def test_live_postgres_pgvector_integration():
    """Gerçek Postgres + pgvector veritabanı entegrasyon testi (#182).

    ENSEMBLE_TEST_PGVECTOR_URL ortam değişkeni tanımlandığında çalışır.
    CREATE EXTENSION vector, DDL, upsert ve <=> kosinüs uzaklığı sorgusunu gerçek DB'de sınar.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    db_url = normalize_database_url(os.environ["ENSEMBLE_TEST_PGVECTOR_URL"])
    engine = create_engine(db_url)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        session.commit()

    index = PgVectorIndex(session_factory, dimensions=2, table_name="test_vector_smoke")
    index.create_schema()
    index.clear()
    index.upsert("live-doc-1", [1.0, 0.0], {"source": "integration-test"})
    results = index.query([1.0, 0.0], k=1)

    assert len(results) == 1
    assert results[0][0] == "live-doc-1"


class _FakeSessionFactory:
    def __init__(self):
        self.calls: list[SimpleNamespace] = []

    def __call__(self) -> "_FakeSession":
        return _FakeSession(self.calls)


class _FakeSession:
    def __init__(self, calls: list[SimpleNamespace]):
        self.calls = calls

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.calls.append(SimpleNamespace(sql=sql, params=params))
        if sql.startswith("SELECT"):
            return _FakeResult([SimpleNamespace(id="near", score=0.99)])
        return _FakeResult([])

    def commit(self) -> None:
        return None


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows
