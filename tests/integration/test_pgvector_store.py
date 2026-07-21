"""Gerçek pgvector adapter testi (#170).

Varsayılan CI dış servise bağımlı kalmaz. `ENSEMBLE_TEST_PGVECTOR_URL` bir
pgvector etkin PostgreSQL DSN'i olduğunda gerçek upsert/query yolu çalışır.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from ensemble.store.vector_store import PgVectorIndex

pytestmark = pytest.mark.integration


def test_pgvector_real_upsert_and_query_contract():
    dsn = os.getenv("ENSEMBLE_TEST_PGVECTOR_URL")
    if not dsn:
        pytest.skip("ENSEMBLE_TEST_PGVECTOR_URL tanımlı değil")

    table_name = f"vector_index_test_{uuid.uuid4().hex}"
    engine = create_engine(dsn, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.execute(
                text(
                    f"""
                    CREATE TABLE {table_name} (
                        id TEXT PRIMARY KEY,
                        embedding vector(2) NOT NULL,
                        meta JSONB NOT NULL DEFAULT '{{}}'::jsonb
                    )
                    """
                )
            )

        index = PgVectorIndex(sessions, dimensions=2, table_name=table_name)
        index.upsert("near", [1.0, 0.0], {"kind": "task"})
        index.upsert("far", [0.0, 1.0], {"kind": "event"})

        results = index.query([1.0, 0.0], k=2)

        assert [document_id for document_id, _score in results] == ["near", "far"]
        assert results[0][1] == pytest.approx(1.0)
        assert results[1][1] == pytest.approx(0.0)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        engine.dispose()
