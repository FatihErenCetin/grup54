from datetime import datetime, timezone

from fastapi.testclient import TestClient

from ensemble.api.deps import get_graph_service
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.engine.graph import GraphService, build_touch_graph
from ensemble.models import NormalizedEvent
from ensemble.store.engine import get_engine
from ensemble.store.models import Base


class _FakeGraphService(GraphService):
    def __init__(self):
        pass  # super().__init__ kasitli atlandi - session_factory gerekmez

    def get_graph(self, window_days=None):
        event = NormalizedEvent(
            id="e1", type="commit", actor="enes", branch="main",
            files=["src/backend/a.py"], ts=datetime.now(timezone.utc), ref="abc",
        )
        return build_touch_graph([event], set(), window_days=window_days or 14)


def _client() -> TestClient:
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_graph_service] = _FakeGraphService
    return TestClient(app)


def test_graph_endpoint_varsayilan_pencere():
    resp = _client().get("/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_days"] == 14
    assert any(n["id"] == "enes" for n in body["nodes"])


def test_graph_endpoint_window_days_query_param():
    resp = _client().get("/graph", params={"window_days": 7})
    assert resp.status_code == 200
    assert resp.json()["window_days"] == 7


def test_graph_endpoint_gercek_di_ile_override_olmadan_500_vermez(tmp_path):
    """#104 review bulgusu (Semih, blocker): eski stub (session_factory=lambda:
    None) override'sız istekte 'NoneType context manager' TypeError'ı veriyordu.
    Gerçek DI (app.py::lifespan) ile artık boş-DB'de bile temiz 200 dönüyor.
    Tablolar burada elle kuruluyor (gerçekte Alembic yapar, `make migrate`)."""
    db_path = tmp_path / "test.db"
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{db_path}")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(settings)
    with TestClient(app) as client:
        resp = client.get("/graph")

    assert resp.status_code == 200
    assert resp.json() == {"window_days": 14, "nodes": [], "edges": []}
