from fastapi.testclient import TestClient

from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.store.vector_store import LocalVectorIndex, PgVectorIndex


def test_lifespan_local_mode_di_wiring():
    settings = Settings(ENSEMBLE_MODE="local")
    app = create_app(settings)

    with TestClient(app):
        # App lifespan runs within TestClient context
        assert hasattr(app.state, "session_factory")
        assert app.state.session_factory is not None
        assert isinstance(app.state.vector_index, LocalVectorIndex)
        assert app.state.radar_service.vector_index is app.state.vector_index
        # #355 — Ask KENDİ indeksini alır. Bu iddia eskiden `is` idi, yani
        # tam olarak hatayı kilitliyordu: paylaşılan tabloda radar'ın
        # `replace_all()`'ı Ask'ın scope/task/decision vektörlerini her
        # rebuild'de sessizce siliyordu (canlıda ölçüldü: 661 satırın
        # 0 tanesi Ask korpusundan).
        assert isinstance(app.state.query_vector_index, LocalVectorIndex)
        assert app.state.query_service.vector_index is app.state.query_vector_index
        assert app.state.query_service.vector_index is not app.state.vector_index


def test_lifespan_hosted_mode_di_wiring():
    settings = Settings(
        ENSEMBLE_MODE="hosted",
        DATABASE_URL="sqlite:///:memory:",
        GEMINI_EMBEDDING_DIMENSIONS=768,
    )
    app = create_app(settings)

    with TestClient(app):
        assert hasattr(app.state, "session_factory")
        assert app.state.session_factory is not None
        assert isinstance(app.state.vector_index, PgVectorIndex)
        assert app.state.vector_index.dimensions == 768
        assert app.state.radar_service.vector_index is app.state.vector_index
        # #355 — hosted'da ayrım TABLO adında görünür: aynı Postgres, AYRI
        # tablo. İkisi de `PgVectorIndex` ama `replace_all()` artık yalnız
        # kendi tablosunu siler.
        assert isinstance(app.state.query_vector_index, PgVectorIndex)
        assert app.state.query_service.vector_index is app.state.query_vector_index
        assert app.state.vector_index.table_name == "vector_index"
        assert app.state.query_vector_index.table_name == "query_vector_index"
