"""Hosted demo tek read-only repo'ya sabitleme testleri (#63 — webhook.py).

`test_webhook.py`'nin gercek-DI fixture desenini kullanir (gecici SQLite +
tablolar onceden kurulu, override YOK) - #104 dersi: stub gercek entegrasyon
hatasini gizleyebiliyor. Repo-pin'in kabul kriteri sadece cevap govdesi degil,
DB'ye GERCEKTEN yazilip yazilmadigi (EventRow sayisi) - repro/statik degil,
gercek session-factory uzerinden dogrulaniyor.
"""

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.store.engine import get_engine
from ensemble.store.models import Base, EventRow

_SECRET = "test-webhook-secret"
_OWNER = "FatihErenCetin"
_REPO = "grup54"


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _push_payload(repo_full_name: str) -> dict:
    return {
        "ref": "refs/heads/T-63-ornek-dal",
        "repository": {"full_name": repo_full_name},
        "commits": [
            {
                "id": "def456",
                "timestamp": "2026-07-23T10:00:00+03:00",
                "author": {"username": "esma6", "name": "Esma"},
                "added": ["src/backend/y.py"],
                "removed": [],
                "modified": [],
            }
        ],
    }


def _make_client(tmp_path, *, demo_mode: bool) -> TestClient:
    db_path = tmp_path / "repo-pin-test.db"
    settings = Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{db_path}",
        GITHUB_WEBHOOK_SECRET=_SECRET,
        DEMO_MODE=demo_mode,
        GITHUB_REPO_OWNER=_OWNER if demo_mode else None,
        GITHUB_REPO_NAME=_REPO if demo_mode else None,
    )
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(settings)
    return TestClient(app)


def _event_count(client: TestClient) -> int:
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        return session.query(EventRow).count()


def test_demo_modda_yabanci_repo_webhooku_yok_sayilir(tmp_path):
    body = json.dumps(_push_payload("baskasi/baska-repo")).encode()
    with _make_client(tmp_path, demo_mode=True) as client:
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "push"},
        )
        assert resp.status_code == 202
        assert resp.json() == {
            "status": "ignored",
            "reason": "repo_not_pinned",
            "event": "push",
        }
        assert _event_count(client) == 0


def test_demo_modda_sabit_repo_webhooku_islenir(tmp_path):
    body = json.dumps(_push_payload(f"{_OWNER}/{_REPO}")).encode()
    with _make_client(tmp_path, demo_mode=True) as client:
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "push"},
        )
        assert resp.status_code == 202
        assert resp.json()["status"] == "accepted"
        assert _event_count(client) == 1


def test_demo_kapali_iken_repo_kontrolu_atlanir(tmp_path):
    # DEMO_MODE=False -> yabanci repo bile ISLENIR (mevcut davranis korunur)
    body = json.dumps(_push_payload("baskasi/baska-repo")).encode()
    with _make_client(tmp_path, demo_mode=False) as client:
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "push"},
        )
        assert resp.status_code == 202
        assert resp.json()["status"] == "accepted"
        assert _event_count(client) == 1


def test_gecersiz_imza_repo_dogru_olsa_da_401(tmp_path):
    # pin kontrolu imza dogrulamasinin ONUNE GECMEZ (siralama guvenlik geriletmesi olmasin)
    body = json.dumps(_push_payload(f"{_OWNER}/{_REPO}")).encode()
    with _make_client(tmp_path, demo_mode=True) as client:
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-Hub-Signature-256": "sha256=" + "0" * 64, "X-GitHub-Event": "push"},
        )
        assert resp.status_code == 401
        assert _event_count(client) == 0
