"""#52 — /events artımlı feed cursor (since / ETag → 304) testleri."""

from datetime import datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from ensemble.api.deps import get_event_service
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.engine.events import EventService
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.models import NormalizedEvent
from ensemble_shared.harness import HarnessPort

_EVENTS = [
    NormalizedEvent(
        id="issue:50", type="issue", actor="enes", branch=None, files=[],
        ts=datetime(2026, 7, 10, 8, 0, 0), ref="50",
    ),
    NormalizedEvent(
        id="commit:aaa", type="commit", actor="esma", branch=None, files=["a.py"],
        ts=datetime(2026, 7, 10, 9, 0, 0), ref="aaa",
    ),
    NormalizedEvent(
        id="pr:99", type="pr", actor="fatih", branch="T-99", files=[],
        ts=datetime(2026, 7, 10, 10, 0, 0), ref="99",
    ),
]


def _service(events: list[NormalizedEvent]) -> EventService:
    return EventService(
        harness_port=MagicMock(spec=HarnessPort),
        github_port=FakeGitHubAdapter(events=list(events)),
    )


# --- servis katmanı -------------------------------------------------------

def test_get_events_without_cursor_returns_full_feed_sorted():
    events, latest_ts, etag = _service(_EVENTS).get_events()
    assert [e.id for e in events] == ["issue:50", "commit:aaa", "pr:99"]  # ts artan
    assert latest_ts == datetime(2026, 7, 10, 10, 0, 0)  # sonraki cursor = en son ts


def test_get_events_with_since_narrows_payload():
    events, latest_ts, etag = _service(_EVENTS).get_events(since=datetime(2026, 7, 10, 9, 0, 0))
    # since dahil (>=): 09:00 ve sonrası
    assert [e.id for e in events] == ["commit:aaa", "pr:99"]


def test_get_events_with_naive_since_works_with_aware_github_data():
    """Fatih'in #241 blocker'ı: naive since ile aware GitHub data'sı karşılaştırılamıyordu.
    
    EventService.get_events() naive datetime alır (router'dan gelir), ama gerçek
    GitHubAdapter aware datetime'larla karşılaştırma yapar → TypeError olmamalı.
    """
    from datetime import timezone
    
    # GitHub'dan aware datetime'la gelen events (gerçek durumu simüle eder)
    aware_events = [
        NormalizedEvent(
            id="evt1", type="commit", actor="user", branch=None, files=["x.py"],
            ts=datetime(2026, 7, 10, 9, 0, 0, tzinfo=timezone.utc), ref="abc",
        ),
        NormalizedEvent(
            id="evt2", type="pr", actor="user2", branch="T-1", files=[],
            ts=datetime(2026, 7, 10, 10, 0, 0, tzinfo=timezone.utc), ref="1",
        ),
    ]
    
    service = _service(aware_events)
    
    # Router'dan naive datetime gelir (FastAPI parse eder)
    naive_since = datetime(2026, 7, 10, 9, 0, 0)  # naive
    
    # Bu çağrı TypeError vermemeli
    events, latest_ts, etag = service.get_events(since=naive_since)
    assert len(events) == 2
    assert events[0].id == "evt1"
    assert events[1].id == "evt2"
    assert latest_ts == datetime(2026, 7, 10, 10, 0, 0)


def test_get_events_empty_feed_echoes_cursor():
    since = datetime(2026, 7, 11, 0, 0, 0)
    events, latest_ts, etag = _service(_EVENTS).get_events(since=since)
    assert events == []
    assert latest_ts == since  # yeni yok → cursor ilerlemez


# --- endpoint (ETag / 304 / since) ---------------------------------------

def _client(events: list[NormalizedEvent]) -> TestClient:
    app = create_app(Settings(DATABASE_URL="sqlite://"))
    app.dependency_overrides[get_event_service] = lambda: _service(events)
    return TestClient(app)


def test_events_endpoint_returns_events_and_etag():
    with _client(_EVENTS) as client:
        r = client.get("/events")
        assert r.status_code == 200
        assert "ETag" in r.headers
        body = r.json()
        assert len(body["events"]) == 3
        assert body["latest_ts"].startswith("2026-07-10T10:00:00")


def test_events_endpoint_if_none_match_returns_304():
    with _client(_EVENTS) as client:
        first = client.get("/events")
        etag = first.headers["ETag"]

        second = client.get("/events", headers={"If-None-Match": etag})
        assert second.status_code == 304
        assert second.headers["ETag"] == etag
        assert second.content == b""


def test_events_endpoint_etag_changes_when_feed_changes():
    with _client(_EVENTS[:2]) as client:
        etag_small = client.get("/events").headers["ETag"]
    with _client(_EVENTS) as client:
        etag_full = client.get("/events").headers["ETag"]
    assert etag_small != etag_full  # içerik değişti → farklı ETag → 304 vermez


def test_events_endpoint_since_query_param_filters():
    with _client(_EVENTS) as client:
        r = client.get("/events", params={"since": "2026-07-10T10:00:00"})
        assert r.status_code == 200
        body = r.json()
        assert [e["id"] for e in body["events"]] == ["pr:99"]


def test_events_polling_flow_returns_304_on_first_incremental_poll():
    """Gerçek istemci akışı: full poll → dönen (latest_ts, ETag) ile ikinci poll.

    Yeni event yoksa ikinci poll doğrudan 304 olmalı. ETag filtrelenmiş tüm
    payload'dan üretilirse cursor ilerledikçe temsil kümesi değişir ve bu poll
    boş yere 200 + gövde döner (#52 CR).
    """
    with _client(_EVENTS) as client:
        first = client.get("/events")
        assert first.status_code == 200
        cursor = first.json()["latest_ts"]
        etag = first.headers["ETag"]

        second = client.get(
            "/events",
            params={"since": cursor},
            headers={"If-None-Match": etag},
        )
        assert second.status_code == 304
        assert second.content == b""
        assert second.headers["ETag"] == etag


def test_events_etag_changes_when_event_added_at_same_latest_ts():
    """Aynı latest_ts'e sonradan eklenen event ETag'i değiştirir → 304'e takılıp kaçmaz."""
    same_ts_event = NormalizedEvent(
        id="commit:zzz", type="commit", actor="semih", branch=None, files=[],
        ts=datetime(2026, 7, 10, 10, 0, 0), ref="zzz",  # pr:99 ile aynı ts
    )
    with _client(_EVENTS) as client:
        etag_before = client.get("/events").headers["ETag"]
    with _client([*_EVENTS, same_ts_event]) as client:
        etag_after = client.get("/events").headers["ETag"]
    assert etag_before != etag_after
