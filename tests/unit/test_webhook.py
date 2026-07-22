"""GitHub webhook receiver (#62) testleri.

HMAC doğrulama (geçerli/geçersiz/eksik imza, timing-safe) + push/pull_request/
issues payload parse + tanınmayan event'in (ping) sessizce yok sayılması.
Gerçek DB'ye (geçici SQLite dosyası, tablolar create_all ile önceden kurulu)
uçtan uca — #104 review dersi: stub/override gerçek entegrasyon hatasını
gizleyebiliyor, bu yüzden en az bir test gerçek DI ile çalışıyor.
"""

import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ensemble.api.routers.webhook import verify_signature
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.integrations.github.normalize import webhook_push_to_events
from ensemble.store.engine import get_engine
from ensemble.store.models import Base, EventRow

_SECRET = "test-webhook-secret"


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "webhook-test.db"
    settings = Settings(
        _env_file=None, DATABASE_URL=f"sqlite:///{db_path}", GITHUB_WEBHOOK_SECRET=_SECRET
    )
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


_PUSH_PAYLOAD = {
    "ref": "refs/heads/T-99-ornek-dal",
    "commits": [
        {
            "id": "abc123",
            "timestamp": "2026-07-20T10:00:00+03:00",
            "author": {"username": "esma6", "name": "Esma"},
            "added": ["src/backend/x.py"],
            "removed": [],
            "modified": ["README.md"],
        }
    ],
}


def test_gecerli_imza_ile_push_islenir(client):
    body = json.dumps(_PUSH_PAYLOAD).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "push"},
    )
    assert resp.status_code == 202
    assert resp.json()["events_processed"] == 1


def test_gecersiz_imza_401_doner(client):
    body = json.dumps(_PUSH_PAYLOAD).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=" + "0" * 64, "X-GitHub-Event": "push"},
    )
    assert resp.status_code == 401


def test_imza_eksikse_401_doner(client):
    body = json.dumps(_PUSH_PAYLOAD).encode()
    resp = client.post("/webhooks/github", content=body, headers={"X-GitHub-Event": "push"})
    assert resp.status_code == 401


def test_sha256_onekisiz_imza_401_doner(client):
    body = json.dumps(_PUSH_PAYLOAD).encode()
    bad = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()  # "sha256=" onekisiz
    resp = client.post(
        "/webhooks/github", content=body, headers={"X-Hub-Signature-256": bad, "X-GitHub-Event": "push"}
    )
    assert resp.status_code == 401


def test_ascii_disi_imza_401_verir_500_degil():
    """Fatih review nit (#62): hmac.compare_digest ASCII-disi str'de TypeError
    atar - fail-closed 401'e cevrilmeli, 500'e sizmamali. HTTP header'lar
    latin-1 tasiyabildigi icin (httpx client-tarafinda ASCII'ye zorluyor,
    gercek ASGI katmani zorlamiyor) fonksiyonu dogrudan cagirip test ediyoruz."""
    settings = Settings(_env_file=None, GITHUB_WEBHOOK_SECRET=_SECRET)
    body = json.dumps(_PUSH_PAYLOAD).encode()

    with pytest.raises(HTTPException) as exc_info:
        verify_signature(settings, body, "sha256=" + "\xe9" * 64)

    assert exc_info.value.status_code == 401


def test_secret_yapilandirilmamissa_503_doner(tmp_path):
    db_path = tmp_path / "no-secret.db"
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{db_path}")  # GITHUB_WEBHOOK_SECRET yok
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(settings)
    with TestClient(app) as test_client:
        body = json.dumps(_PUSH_PAYLOAD).encode()
        resp = test_client.post(
            "/webhooks/github",
            content=body,
            headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "push"},
        )
    assert resp.status_code == 503


def test_bozuk_json_400_doner(client):
    body = b"{bozuk-json"
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "push"},
    )
    assert resp.status_code == 400


def test_taninmayan_event_sessizce_yoksayilir(client):
    """ping (webhook ilk kurulumda GitHub'ın gönderdiği test event'i) 202 ile
    yoksayılır — GitHub webhook'u 'bozuk' sanmasın."""
    body = json.dumps({"zen": "Anything added dilutes everything else."}).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "ping"},
    )
    assert resp.status_code == 202
    assert resp.json() == {"status": "ignored", "event": "ping"}


def test_pull_request_event_islenir(client):
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "updated_at": "2026-07-20T10:00:00Z",
            "user": {"login": "esma6"},
            "head": {"ref": "T-99-ornek-dal"},
        },
    }
    body = json.dumps(payload).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 202
    assert resp.json()["events_processed"] == 1


def test_issues_event_islenir(client):
    payload = {
        "action": "opened",
        "issue": {
            "number": 62,
            "updated_at": "2026-07-20T10:00:00Z",
            "user": {"login": "esma6"},
        },
    }
    body = json.dumps(payload).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 202
    assert resp.json()["events_processed"] == 1


def test_islenen_event_db_ye_gercekten_yaziliyor(client):
    """#104 dersi: override yok, gercek session-factory - DB'ye gercekten
    yazildigini dogrudan sorgulayarak kanitla."""
    body = json.dumps(_PUSH_PAYLOAD).encode()
    client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "push"},
    )
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        rows = session.query(EventRow).all()
    assert len(rows) == 1
    assert rows[0].id == "commit:abc123"


# --- webhook_push_to_events (saf fonksiyon) ---


def test_webhook_push_to_events_dosyalari_birlestirir():
    events = webhook_push_to_events(_PUSH_PAYLOAD)
    assert len(events) == 1
    event = events[0]
    assert event.branch == "T-99-ornek-dal"
    assert set(event.files) == {"src/backend/x.py", "README.md"}
    assert event.actor == "esma6"


def test_webhook_push_to_events_bos_commits_bos_liste():
    assert webhook_push_to_events({"ref": "refs/heads/main", "commits": []}) == []
