from __future__ import annotations

from types import SimpleNamespace

import pytest

from ensemble.config import Settings
from ensemble.ports import VectorIndexPort
from ensemble.store.vector_store import (
    LocalVectorIndex,
    PgVectorIndex,
    _to_pgvector_literal,
    build_vector_index,
)


def vector_index_contract(index: VectorIndexPort) -> None:
    index.upsert("near", [1.0, 0.0], {"path": "a.py"})
    index.upsert("far", [0.0, 1.0], {"path": "b.py"})
    index.upsert("also-near", [0.9, 0.1], {"path": "c.py"})

    results = index.query([1.0, 0.0], k=2)

    assert [id for id, _score in results] == ["near", "also-near"]


def test_local_vector_index_contract():
    vector_index_contract(LocalVectorIndex())


def test_build_vector_index_uses_local_index_in_local_mode():
    settings = Settings(ENSEMBLE_MODE="local")

    index = build_vector_index(settings)

    assert isinstance(index, LocalVectorIndex)


def test_build_vector_index_uses_pgvector_in_hosted_mode():
    settings = Settings(ENSEMBLE_MODE="hosted", GEMINI_EMBEDDING_DIMENSIONS=2)

    index = build_vector_index(settings, session_factory=FakeSessionFactory())

    assert isinstance(index, PgVectorIndex)


def test_build_vector_index_requires_session_factory_for_hosted_mode():
    settings = Settings(ENSEMBLE_MODE="hosted")

    with pytest.raises(ValueError, match="session_factory"):
        build_vector_index(settings)


def test_pgvector_index_emits_pgvector_upsert_and_query_sql():
    sessions = FakeSessionFactory()
    index = PgVectorIndex(sessions, dimensions=2)

    index.create_schema()
    index.upsert("doc", [1.0, 0.0], {"path": "a.py"})
    results = index.query([1.0, 0.0], k=2)

    statements = [call.sql for call in sessions.calls]
    params = [call.params for call in sessions.calls]
    assert "CREATE TABLE IF NOT EXISTS vector_index" in statements[0]
    assert "embedding vector(2)" in statements[0]
    assert "CAST(:embedding AS vector)" in statements[1]
    assert "ON CONFLICT (id) DO UPDATE" in statements[1]
    assert params[1]["embedding"] == "[1.0,0.0]"
    assert params[1]["meta"] == '{"path": "a.py"}'
    assert "ORDER BY embedding <=> CAST(:embedding AS vector), id" in statements[2]
    assert params[2] == {"embedding": "[1.0,0.0]", "k": 2}
    assert results == [("near", 0.99), ("also-near", 0.9)]


def test_pgvector_index_emits_truncate_table_on_clear():
    sessions = FakeSessionFactory()
    index = PgVectorIndex(sessions, dimensions=2)

    index.clear()

    statements = [call.sql for call in sessions.calls]
    assert "TRUNCATE TABLE vector_index" in statements[0]


def test_pgvector_index_validates_dimensions_before_sql():
    sessions = FakeSessionFactory()
    index = PgVectorIndex(sessions, dimensions=2)

    with pytest.raises(ValueError, match="configured dimensions"):
        index.upsert("bad", [1.0], {})

    assert sessions.calls == []


def test_pgvector_literal_is_plain_vector_text():
    assert _to_pgvector_literal([1, 0.25, -0.5]) == "[1.0,0.25,-0.5]"


class FakeSessionFactory:
    def __init__(self):
        self.calls: list[SimpleNamespace] = []

    def __call__(self) -> "FakeSession":
        return FakeSession(self.calls)


class FakeSession:
    def __init__(self, calls: list[SimpleNamespace]):
        self.calls = calls

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.calls.append(SimpleNamespace(sql=sql, params=params))
        if sql.startswith("SELECT"):
            return FakeResult(
                [
                    SimpleNamespace(id="near", score=0.99),
                    SimpleNamespace(id="also-near", score=0.9),
                ]
            )
        return FakeResult([])

    def commit(self) -> None:
        return None


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows
