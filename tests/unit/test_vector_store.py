from __future__ import annotations

from types import SimpleNamespace

import pytest

from ensemble.config import Settings
from ensemble.ports import VectorIndexPort
from ensemble.store.vector_store import (
    FaissVectorIndex,
    LocalVectorIndex,
    QUERY_VECTOR_TABLE,
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


def test_faiss_vector_index_contract():
    pytest.importorskip("faiss")
    pytest.importorskip("numpy")

    vector_index_contract(FaissVectorIndex(dimensions=2))


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

    index.upsert("doc", [1.0, 0.0], {"path": "a.py"})
    results = index.query([1.0, 0.0], k=2)

    statements = [call.sql for call in sessions.calls]
    params = [call.params for call in sessions.calls]
    # DDL artık migration'da; PgVectorIndex yalnız DML üretir
    assert "CAST(:embedding AS vector)" in statements[0]
    assert "ON CONFLICT (id) DO UPDATE" in statements[0]
    assert params[0]["embedding"] == "[1.0,0.0]"
    assert params[0]["meta"] == '{"path": "a.py"}'
    assert "ORDER BY embedding <=> CAST(:embedding AS vector), id" in statements[1]
    # T-79: repo_full_name=None (tek-kiracılı çağrı) yine de params sözlüğünde
    # taşınır (SQL'de WHERE'siz kalsa da) — PgVectorIndex her çağrıda AYNI
    # params şeklini üretir, yalnız SQL metni repo_full_name'e göre dallanır.
    assert params[1] == {"embedding": "[1.0,0.0]", "k": 2, "repo_full_name": None}
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


def test_replace_all_YALNIZ_kendi_tablosuna_dokunur():
    """#355 — radar'ın rebuild'i Ask'ın vektörlerini silmemeli.

    Canlıda ölçülen sessiz hata (30 Tem 2026): radar ile Ask AYNI
    `vector_index` tablosunu paylaşıyordu. Radar'ın rebuild'i
    `replace_all()` çağırır ve sözleşmesi gereği tabloyu KOMPLE siler —
    Ask'ın scope/task/decision vektörleri her rebuild'de yok oluyordu.

    Sessiz olmasının sebebi `QueryService._indexed_hashes`'in bellekte
    olması: süreç "zaten gömdüm" sanıp yeniden gömmüyor, vektör sorgusu
    yalnız olay id'leri dönüyor, Ask korpusuna filtrelenince boş kalıyor
    ve İSTİSNA FIRLAMADIĞI için `degraded` de dolmuyordu.

    Ölçüm: `vector_index` 661 satır (378 commit + 149 pr + 134 issue),
    Ask korpusundan (`task:`/`scope:`/`decision:`) 0 satır.

    MUTASYON KİLİDİ: `replace_all`/`clear`'daki `{self.table_name}`'i sabit
    `vector_index`e çevir -> bu test kırılır.
    """
    ask_sessions = FakeSessionFactory()
    ask = PgVectorIndex(
        ask_sessions, dimensions=2, table_name="query_vector_index", repo_full_name="o/r"
    )
    ask.replace_all([("decision:D-46", [1.0, 0.0], {"type": "decision"})])

    ifadeler = " ".join(call.sql for call in ask_sessions.calls)
    assert "query_vector_index" in ifadeler
    # Radar'ın tablosuna TEK BİR ifade bile gitmemeli
    assert "FROM vector_index" not in ifadeler
    assert "TRUNCATE vector_index" not in ifadeler
    assert "INTO vector_index" not in ifadeler


def test_build_vector_index_ask_tablosunu_ayri_kurar():
    """Fabrika `table_name`'i GEÇİRİR — DI'da ayrım burada başlıyor.

    MUTASYON KİLİDİ: `build_vector_index`'te `table_name=table_name`
    argümanını sil -> Ask yine radar'ın tablosuna yazar, bu test kırılır.
    """
    sessions = FakeSessionFactory()
    settings = Settings(ENSEMBLE_MODE="hosted", GEMINI_EMBEDDING_DIMENSIONS=2)
    radar = build_vector_index(settings, session_factory=sessions)
    ask = build_vector_index(
        settings, session_factory=sessions, table_name=QUERY_VECTOR_TABLE
    )
    assert isinstance(radar, PgVectorIndex) and isinstance(ask, PgVectorIndex)
    assert radar.table_name == "vector_index"
    assert ask.table_name == "query_vector_index"
    assert radar.table_name != ask.table_name
