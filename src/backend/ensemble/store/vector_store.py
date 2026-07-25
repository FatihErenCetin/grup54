from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ensemble.config import Settings
from ensemble.engine.vectorstore import InMemoryVectorIndex
from ensemble.ports import VectorIndexPort


class LocalVectorIndex(InMemoryVectorIndex):
    """Local VectorIndexPort implementation used by the MVP cache."""


class FaissVectorIndex:
    """Optional FAISS-backed local index.

    FAISS is intentionally optional because it is a binary dependency. The repo's
    default local implementation remains LocalVectorIndex; this adapter becomes
    active only when faiss-cpu is installed by the environment.
    """

    def __init__(self, dimensions: int):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")

        try:
            import faiss  # type: ignore[import-not-found]
            import numpy as np  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("faiss-cpu and numpy are required for FaissVectorIndex") from exc

        self.dimensions = dimensions
        self._faiss = faiss
        self._np = np
        self._ids: list[str] = []
        self._vectors: dict[str, list[float]] = {}
        self._meta: dict[str, dict] = {}
        self._index = faiss.IndexFlatIP(dimensions)

    def upsert(self, id: str, vec: list[float], meta: dict) -> None:
        _validate_vector_record(id, vec)
        self._validate_dimensions(vec)
        self._vectors[id] = list(vec)
        self._meta[id] = dict(meta)
        self._rebuild()

    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]:
        if k <= 0:
            return []
        if not vec:
            raise ValueError("vec must not be empty")
        self._validate_dimensions(vec)
        if not self._ids:
            return []

        query = self._to_unit_matrix([vec])
        scores, positions = self._index.search(query, len(self._ids))
        scored = [
            (self._ids[position], float(score))
            for score, position in zip(scores[0], positions[0])
            if position >= 0
        ]
        return sorted(scored, key=lambda item: (-item[1], item[0]))[:k]

    def meta(self, id: str) -> dict:
        return dict(self._meta[id])

    def clear(self) -> None:
        self._ids.clear()
        self._vectors.clear()
        self._meta.clear()
        self._index = self._faiss.IndexFlatIP(self.dimensions)

    def _validate_dimensions(self, vec: list[float]) -> None:
        if len(vec) != self.dimensions:
            raise ValueError("vectors must have the configured dimensions")

    def _rebuild(self) -> None:
        self._ids = sorted(self._vectors)
        self._index = self._faiss.IndexFlatIP(self.dimensions)
        if self._ids:
            self._index.add(self._to_unit_matrix([self._vectors[id] for id in self._ids]))

    def _to_unit_matrix(self, vectors: list[list[float]]) -> Any:
        matrix = self._np.array(vectors, dtype="float32")
        self._faiss.normalize_L2(matrix)
        return matrix

    def replace_all(
        self,
        vectors: list[tuple[str, list[float], dict]],
        *,
        session: Session | None = None,
    ) -> None:
        # session in-memory FAISS icin kullanilmaz. Once tumunu validate edip
        # yeni sozlukleri kur, sonra tek atamayla degistir (atomik build-then-swap).
        new_vectors: dict[str, list[float]] = {}
        new_meta: dict[str, dict] = {}
        for vid, vec, meta in vectors:
            _validate_vector_record(vid, vec)
            self._validate_dimensions(vec)
            new_vectors[vid] = list(vec)
            new_meta[vid] = dict(meta)
        self._vectors = new_vectors
        self._meta = new_meta
        self._rebuild()


class PgVectorIndex:
    """PostgreSQL pgvector implementation of VectorIndexPort."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        dimensions: int,
        table_name: str = "vector_index",
    ):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if not table_name.isidentifier():
            raise ValueError("table_name must be a plain SQL identifier")

        self.session_factory = session_factory
        self.dimensions = dimensions
        self.table_name = table_name

    def create_schema(self) -> None:
        ddl = text(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id TEXT PRIMARY KEY,
                embedding vector({self.dimensions}) NOT NULL,
                meta JSONB NOT NULL DEFAULT '{{}}'::jsonb
            )
            """
        )
        with self.session_factory() as session:
            session.execute(ddl)
            session.commit()

    def upsert(self, id: str, vec: list[float], meta: dict) -> None:
        _validate_vector_record(id, vec)
        self._validate_dimensions(vec)

        stmt = text(
            f"""
            INSERT INTO {self.table_name} (id, embedding, meta)
            VALUES (:id, CAST(:embedding AS vector), CAST(:meta AS jsonb))
            ON CONFLICT (id) DO UPDATE
            SET embedding = EXCLUDED.embedding,
                meta = EXCLUDED.meta
            """
        )
        params = {
            "id": id,
            "embedding": _to_pgvector_literal(vec),
            "meta": json.dumps(meta, sort_keys=True),
        }
        with self.session_factory() as session:
            session.execute(stmt, params)
            session.commit()

    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]:
        if k <= 0:
            return []
        if not vec:
            raise ValueError("vec must not be empty")
        self._validate_dimensions(vec)

        stmt = text(
            f"""
            SELECT id, 1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM {self.table_name}
            ORDER BY embedding <=> CAST(:embedding AS vector), id
            LIMIT :k
            """
        )
        params = {"embedding": _to_pgvector_literal(vec), "k": k}
        with self.session_factory() as session:
            rows = session.execute(stmt, params).all()

        return [(str(row.id), float(row.score)) for row in rows]

    def clear(self) -> None:
        stmt = text(f"TRUNCATE TABLE {self.table_name}")
        with self.session_factory() as session:
            session.execute(stmt)
            session.commit()

    def replace_all(
        self,
        vectors: list[tuple[str, list[float], dict]],
        *,
        session: Session | None = None,
    ) -> None:
        """vector_index tablosunu TRUNCATE + toplu INSERT ile atomik yeniden kurar.

        `session` verilirse (rebuild akışı, #218): TRUNCATE+INSERT çağıranın
        DB transaction'ına yazılır ve commit ÇAĞIRANA bırakılır → DB satırları
        (events) ile vektörler tek commit'te birlikte kalır ya da birlikte geri
        alınır (DB güncellenip index eski kalmaz). `session` verilmezse kendi
        transaction'ını açıp commit eder (bağımsız kullanım).
        """
        truncate_stmt = text(f"TRUNCATE {self.table_name}")
        insert_stmt = text(
            f"""
            INSERT INTO {self.table_name} (id, embedding, meta)
            VALUES (:id, CAST(:embedding AS vector), CAST(:meta AS jsonb))
            ON CONFLICT (id) DO UPDATE
            SET embedding = EXCLUDED.embedding,
                meta = EXCLUDED.meta
            """
        )

        for vid, vec, meta in vectors:
            _validate_vector_record(vid, vec)
            self._validate_dimensions(vec)

        def _apply(sess: Session) -> None:
            sess.execute(truncate_stmt)
            for vid, vec, meta in vectors:
                params = {
                    "id": vid,
                    "embedding": _to_pgvector_literal(vec),
                    "meta": json.dumps(meta, sort_keys=True),
                }
                sess.execute(insert_stmt, params)

        if session is not None:
            # Çağıranın transaction'ına katıl — commit'i çağıran yapar (atomik).
            _apply(session)
        else:
            with self.session_factory() as own_session:
                _apply(own_session)
                own_session.commit()

    def _validate_dimensions(self, vec: list[float]) -> None:
        if len(vec) != self.dimensions:
            raise ValueError("vectors must have the configured dimensions")


def build_vector_index(
    settings: Settings,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> VectorIndexPort:
    if settings.ENSEMBLE_MODE == "hosted":
        if session_factory is None:
            raise ValueError("session_factory is required for hosted vector index")
        return PgVectorIndex(
            session_factory,
            dimensions=settings.GEMINI_EMBEDDING_DIMENSIONS,
        )

    return LocalVectorIndex()


def _validate_vector_record(id: str, vec: list[float]) -> None:
    if not id:
        raise ValueError("id must not be empty")
    if not vec:
        raise ValueError("vec must not be empty")


def _to_pgvector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vec) + "]"


_check_local: VectorIndexPort = LocalVectorIndex()
_check_pg: VectorIndexPort = PgVectorIndex(lambda: Session(), dimensions=1)
