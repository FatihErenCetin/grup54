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
        assert app.state.query_service.vector_index is app.state.vector_index


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
        assert app.state.query_service.vector_index is app.state.vector_index
