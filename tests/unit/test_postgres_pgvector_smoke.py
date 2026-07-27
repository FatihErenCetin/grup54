"""SQL-Şekil ve Gerçek DB Smoke Test Suite for Postgres + pgvector provision (#182)."""

import os
import pytest

from ensemble.store.engine import normalize_database_url
from ensemble.store.vector_store import PgVectorIndex



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

    try:
        with session_factory() as session:
            session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            session.execute(text("DROP TABLE IF EXISTS test_vector_smoke;"))
            session.execute(text("CREATE TABLE test_vector_smoke (id VARCHAR PRIMARY KEY, embedding vector(2), meta JSONB);"))
            session.commit()

        index = PgVectorIndex(session_factory, dimensions=2, table_name="test_vector_smoke")

        index.upsert("near", [1.0, 0.0], {"source": "integration-test"})
        index.upsert("far", [0.0, 1.0], {"source": "integration-test"})

        results = index.query([1.0, 0.0], k=2)

        assert len(results) == 2
        # ORDER BY behavior testing
        assert results[0][0] == "near"
        assert results[1][0] == "far"
        # Score semantic testing
        assert results[0][1] > results[1][1]
    finally:
        with session_factory() as session:
            session.execute(text("DROP TABLE IF EXISTS test_vector_smoke;"))
            session.commit()



