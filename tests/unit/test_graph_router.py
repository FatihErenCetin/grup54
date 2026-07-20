from datetime import datetime, timezone

from fastapi.testclient import TestClient

from ensemble.api.deps import get_graph_service
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.engine.graph import GraphService, build_touch_graph
from ensemble.models import NormalizedEvent


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
