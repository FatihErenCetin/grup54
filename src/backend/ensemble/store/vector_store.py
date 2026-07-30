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

    def fingerprints(self) -> dict[str, str]:
        """Bkz. `VectorIndexPort.fingerprints`. FAISS indeksi süreçle birlikte
        yaşar; parmak izleri de öyle — tutarlı ve dürüst."""
        return {
            id: str(meta["fingerprint"])
            for id, meta in self._meta.items()
            if meta.get("fingerprint")
        }

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
    """PostgreSQL pgvector implementation of VectorIndexPort.

    `repo_full_name` (T-79, çok-kiracılık): `vector_index` tablosu artık
    `(id, repo_full_name)` composite PK taşıyor (bkz. migration
    a1f7c9d4e2b6) — `id` tek başına global benzersiz DEĞİL (örn.
    "task:T-51" her repoda ayrı bir görev olabilir). `VectorIndexPort`
    SÖZLEŞMESİ (upsert/query/clear/replace_all imzaları) BİLEREK
    DEĞİŞTİRİLMEDİ — engine/query.py (QueryService) bu port'u çağıran TEK
    yer ve tenant scoping'ten HABERSİZ kalmalı (engine sıfır dokunuş). Bunun
    yerine her kiracı KENDİ `PgVectorIndex(..., repo_full_name=<repo>)`
    örneğini alır (bkz. ensemble/tenancy.py) — kiracı bilgisi CONSTRUCTOR'da
    bağlanır, her çağrıda parametre olarak geçilmez (GitHubAdapter'ın
    owner/repo'yu constructor'da bağlamasıyla AYNI desen).

    `repo_full_name=None` (varsayılan) geriye dönük uyumluluk için — mevcut
    tek-kiracılı testler/çağrılar etkilenmez, ama o modda WHERE'siz
    sorgu/upsert TÜM kiracıların satırlarına dokunur (yalnız yerel/eski
    testlerde kullanılmalı; üretim DI'sı HER ZAMAN açıkça bir repo_full_name
    verir).
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        dimensions: int,
        table_name: str = "vector_index",
        repo_full_name: str | None = None,
    ):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if not table_name.isidentifier():
            raise ValueError("table_name must be a plain SQL identifier")

        self.session_factory = session_factory
        self.dimensions = dimensions
        self.table_name = table_name
        self.repo_full_name = repo_full_name

    def upsert(self, id: str, vec: list[float], meta: dict) -> None:
        _validate_vector_record(id, vec)
        self._validate_dimensions(vec)

        if self.repo_full_name is not None:
            stmt = text(
                f"""
                INSERT INTO {self.table_name} (id, repo_full_name, embedding, meta)
                VALUES (:id, :repo_full_name, CAST(:embedding AS vector), CAST(:meta AS jsonb))
                ON CONFLICT (id, repo_full_name) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    meta = EXCLUDED.meta
                """
            )
        else:
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
            "repo_full_name": self.repo_full_name,
            "embedding": _to_pgvector_literal(vec),
            "meta": json.dumps(meta, sort_keys=True),
        }
        with self.session_factory() as session:
            session.execute(stmt, params)
            session.commit()

    def fingerprints(self) -> dict[str, str]:
        """Bkz. `VectorIndexPort.fingerprints` — TEK sorguda tüm parmak izleri.

        `meta->>'fingerprint'` NULL olan satırlar atlanır: bunlar alan
        eklenmeden ÖNCE yazılmış eski satırlardır. Onları "parmak izi yok"
        saymak, ilk turda bir kez yeniden gömülmelerine yol açar ve sonrası
        kalıcı olur — uydurma bir parmak izi atamaktan (hep taze sanılır,
        değişiklik BİR DAHA hiç yakalanmaz) çok daha güvenli yönde yanılma.
        """
        where_clause = (
            "WHERE repo_full_name = :repo_full_name" if self.repo_full_name is not None else ""
        )
        stmt = text(
            f"""
            SELECT id, meta->>'fingerprint' AS fingerprint
            FROM {self.table_name}
            {where_clause}
            """
        )
        with self.session_factory() as session:
            rows = session.execute(stmt, {"repo_full_name": self.repo_full_name}).all()
        return {row[0]: row[1] for row in rows if row[1]}

    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]:
        if k <= 0:
            return []
        if not vec:
            raise ValueError("vec must not be empty")
        self._validate_dimensions(vec)

        where_clause = "WHERE repo_full_name = :repo_full_name" if self.repo_full_name is not None else ""
        stmt = text(
            f"""
            SELECT id, 1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM {self.table_name}
            {where_clause}
            ORDER BY embedding <=> CAST(:embedding AS vector), id
            LIMIT :k
            """
        )
        params = {"embedding": _to_pgvector_literal(vec), "k": k, "repo_full_name": self.repo_full_name}
        with self.session_factory() as session:
            rows = session.execute(stmt, params).all()

        return [(str(row.id), float(row.score)) for row in rows]

    def clear(self) -> None:
        if self.repo_full_name is not None:
            stmt = text(f"DELETE FROM {self.table_name} WHERE repo_full_name = :repo_full_name")
            params = {"repo_full_name": self.repo_full_name}
        else:
            stmt = text(f"TRUNCATE TABLE {self.table_name}")
            params = {}
        with self.session_factory() as session:
            session.execute(stmt, params)
            session.commit()

    def replace_all(
        self,
        vectors: list[tuple[str, list[float], dict]],
        *,
        session: Session | None = None,
    ) -> None:
        """`vector_index` tablosunu (yalnız BU kiracının satırlarını) TRUNCATE/
        DELETE + toplu INSERT ile atomik yeniden kurar.

        `repo_full_name` verilmişse TRUNCATE yerine `DELETE ... WHERE
        repo_full_name=...` kullanılır — TRUNCATE tüm tabloyu (diğer
        kiracıların vektörlerini de) silerdi (izolasyon ihlali).

        `session` verilirse (rebuild akışı, #218): yazma çağıranın DB
        transaction'ına katılır ve commit ÇAĞIRANA bırakılır → DB satırları
        (events) ile vektörler tek commit'te birlikte kalır ya da birlikte
        geri alınır. `session` verilmezse kendi transaction'ını açıp commit
        eder (bağımsız kullanım).
        """
        if self.repo_full_name is not None:
            clear_stmt = text(f"DELETE FROM {self.table_name} WHERE repo_full_name = :repo_full_name")
            clear_params = {"repo_full_name": self.repo_full_name}
            insert_stmt = text(
                f"""
                INSERT INTO {self.table_name} (id, repo_full_name, embedding, meta)
                VALUES (:id, :repo_full_name, CAST(:embedding AS vector), CAST(:meta AS jsonb))
                ON CONFLICT (id, repo_full_name) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    meta = EXCLUDED.meta
                """
            )
        else:
            clear_stmt = text(f"TRUNCATE {self.table_name}")
            clear_params = {}
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
            sess.execute(clear_stmt, clear_params)
            for vid, vec, meta in vectors:
                params = {
                    "id": vid,
                    "repo_full_name": self.repo_full_name,
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
    repo_full_name: str | None = None,
    table_name: str = "vector_index",
) -> VectorIndexPort:
    """`repo_full_name` verilirse (T-79) hosted `PgVectorIndex` o kiracıya
    SABİTLENİR (bkz. `PgVectorIndex` docstring'i); local `LocalVectorIndex`
    zaten her kiracı için AYRI bir Python nesnesi olduğundan (bkz.
    ensemble/tenancy.py) ek bir parametreye ihtiyaç duymaz — bellek-içi
    izolasyon kendiliğinden sağlanır.

    `table_name` (#355): radar ile Ask AYRI tablo kullanır. Paylaştıklarında
    radar'ın `replace_all()`'ı (sözleşmesi gereği "hepsini değiştir") Ask'ın
    scope/task/decision vektörlerini her rebuild'de siliyordu — ve
    `_indexed_hashes` bellekte olduğu için Ask bunu FARK ETMİYOR, istisna
    fırlamadığı için `degraded` de dolmuyordu. Gerekçenin tamamı
    `migrations/versions/e5b8d2c71a09_query_vector_index.py` başlığında.
    Local modda ayrım zaten bedava: her çağrı AYRI bir `LocalVectorIndex`
    nesnesi döndürür."""
    if settings.ENSEMBLE_MODE == "hosted":
        if session_factory is None:
            raise ValueError("session_factory is required for hosted vector index")
        return PgVectorIndex(
            session_factory,
            dimensions=settings.GEMINI_EMBEDDING_DIMENSIONS,
            repo_full_name=repo_full_name,
            table_name=table_name,
        )

    return LocalVectorIndex()


#: Ask korpusunun vektör tablosu — radar'ınkinden AYRI (#355).
QUERY_VECTOR_TABLE = "query_vector_index"


def _validate_vector_record(id: str, vec: list[float]) -> None:
    if not id:
        raise ValueError("id must not be empty")
    if not vec:
        raise ValueError("vec must not be empty")


def _to_pgvector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vec) + "]"


_check_local: VectorIndexPort = LocalVectorIndex()
_check_pg: VectorIndexPort = PgVectorIndex(lambda: Session(), dimensions=1)
