from datetime import datetime, timezone

from fastapi.testclient import TestClient

from ensemble.api.deps import get_query_service
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.models import Citation, NearestRef, QueryResult, SearchReceipt


class _QueryService:
    def ask(self, question: str) -> QueryResult:
        return QueryResult(
            answer=f"{question} kapsamda [cite:T-58]",
            citations=[
                Citation(
                    type="task",
                    ref="T-58",
                    quote="Ask endpoint'ini yaz",
                    n=1,
                )
            ],
            as_of=datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
            last_commit="abc1234",
            confidence="high",
            status="answered",
            searched=[SearchReceipt(type="task", count=1)],
            nearest=[NearestRef(type="task", ref="T-58")],
        )


def test_query_router_zengin_kontrati_tasir():
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_query_service] = _QueryService

    response = TestClient(app).get("/query", params={"q": "Ask nedir?"})

    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["citations"][0]["ref"] == "T-58"
    assert response.json()["as_of"] == "2026-07-21T12:00:00Z"
    assert response.json()["last_commit"] == "abc1234"


def test_query_router_bos_parametreyi_422_reddeder():
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_query_service] = _QueryService

    response = TestClient(app).get("/query", params={"q": ""})

    assert response.status_code == 422
