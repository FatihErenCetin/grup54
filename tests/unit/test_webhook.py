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

from ensemble.api.routers import webhook as webhook_module
from ensemble.api.routers.webhook import verify_signature
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.integrations.github.normalize import webhook_push_to_events
from ensemble.store.engine import get_engine
from ensemble.store.models import (
    DEFAULT_REPO_FULL_NAME,
    Base,
    EventRow,
    TaskProjectionRow,
    TaskStatusEventRow,
)

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


# --- D-55 (İş 3, GOREV 3/4): webhook -> transitions_from_webhook -> apply_transitions ---
#
# Bugün canlıda ölçülen arızanın (T-158 dosyada "todo" ama issue #158 kapalıydı)
# birebir regresyon kilidi: webhook -> Projector.apply_transitions -> GET /board.


def _seed_task(session_factory, task_id: str, status: str = "todo", title: str = "Görev") -> None:
    # T-79: bu dosyanın `client` fixture'ı GITHUB_REPO_OWNER/NAME vermiyor —
    # webhook.py bu durumda DEFAULT_REPO_FULL_NAME'e düşer (payload'da da
    # `repository` yoksa); tohum satır AYNI kiracıyla açılmalı.
    with session_factory() as session:
        session.add(
            TaskProjectionRow(
                task_id=task_id,
                repo_full_name=DEFAULT_REPO_FULL_NAME,
                title=title,
                status=status,
                seed_status=status,
            )
        )
        session.commit()


def _board_status(client: TestClient, task_id: str) -> str | None:
    resp = client.get("/board")
    assert resp.status_code == 200
    for card in resp.json()["cards"]:
        if card["task_id"] == task_id:
            return card["status"]
    return None


def test_kapanan_issue_karti_done_yapar(client):
    """`x_github_event=issues` + `action=closed` -> GET /board T-158'i `done` gösterir.

    MUTASYON KILIDI (2/3): webhook.py'den `transitions_from_webhook` çağrısı
    SİLİNİRSE bu test KIRMIZI olmalı.
    """
    _seed_task(client.app.state.session_factory, "T-158", status="todo")

    payload = {
        "action": "closed",
        "issue": {"number": 158, "updated_at": "2026-07-25T09:00:00Z", "user": {"login": "esma"}},
    }
    body = json.dumps(payload).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["applied"] == 1
    assert data["unmatched"] == 0

    assert _board_status(client, "T-158") == "done"


def test_merge_edilen_pr_govdesindeki_closes_ile_karti_done_yapar(client):
    """`pull_request` + `action=closed` + `merged=true` + gövdede `Closes #158`
    -> aynı sonuç (T-158 `done`). Ardından AYNI payload TEKRAR gönderildiğinde
    (GitHub redelivery) `task_status_events` ÇOĞALMAZ ve board DEĞİŞMEZ."""
    _seed_task(client.app.state.session_factory, "T-158", status="todo")

    payload = {
        "action": "closed",
        "pull_request": {
            "number": 258,
            "updated_at": "2026-07-25T11:00:00Z",
            "user": {"login": "fatih"},
            "head": {"ref": "hotfix-alakasiz-dal"},  # T-<id> DEĞİL — yalnız Closes #158 geçiş üretsin
            "body": "Closes #158",
            "merged": True,
        },
    }
    body = json.dumps(payload).encode()
    headers = {"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"}

    resp1 = client.post("/webhooks/github", content=body, headers=headers)
    assert resp1.status_code == 202
    assert resp1.json()["applied"] == 1
    assert _board_status(client, "T-158") == "done"

    def _status_event_count() -> int:
        with client.app.state.session_factory() as session:
            return session.query(TaskStatusEventRow).count()

    assert _status_event_count() == 1

    # Redelivery: GitHub aynı webhook'u tekrar gönderebilir (retry/at-least-once).
    resp2 = client.post("/webhooks/github", content=body, headers=headers)
    assert resp2.status_code == 202
    assert resp2.json()["applied"] == 0
    assert resp2.json()["unchanged"] == 1
    assert _status_event_count() == 1  # çoğalmadı
    assert _board_status(client, "T-158") == "done"  # board değişmedi


def test_eslesmeyen_task_id_webhook_uzerinden_unmatched_sayilir(client):
    """.harness'te (task_projection'da) karşılığı olmayan bir task_id için
    webhook 202 + `unmatched=1` döner — sessizce yutulmaz, kart da uydurulmaz."""
    payload = {
        "action": "closed",
        "issue": {"number": 424242, "updated_at": "2026-07-25T09:00:00Z", "user": {"login": "esma"}},
    }
    body = json.dumps(payload).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["applied"] == 0
    assert data["unmatched"] == 1
    assert _board_status(client, "T-424242") is None


def test_events_bos_ama_transitions_dolu_olsa_bile_gecisler_uygulanir(client, monkeypatch):
    """`parse_events` (NormalizedEvent üretimi) boş dönse bile
    `transitions_from_webhook` (StatusTransition üretimi) doluysa geçişler
    YİNE DE uygulanır — biri diğerini sessizce yutmaz (D-55 kabul kriteri).
    Gerçek payload'larda ikisi birlikte boş/dolu olma eğiliminde olduğu için
    ayrışmayı doğrudan kilitlemek amacıyla `parse_events` monkeypatch'lenir."""
    _seed_task(client.app.state.session_factory, "T-158", status="todo")
    monkeypatch.setattr(webhook_module, "parse_events", lambda event_type, payload: [])

    payload = {
        "action": "closed",
        "issue": {"number": 158, "updated_at": "2026-07-25T09:00:00Z", "user": {"login": "esma"}},
    }
    body = json.dumps(payload).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["events_processed"] == 0
    assert data["applied"] == 1
    assert _board_status(client, "T-158") == "done"


def test_demo_modda_yabanci_repo_icin_transitions_de_uygulanmaz(tmp_path):
    """`test_demo_repo_pin.py::test_demo_modda_yabanci_repo_webhooku_yok_sayilir`
    yalnız `EventRow` sayısını (0) kilitler — bu görev (D-55, İş 3) yeni bir
    yazma yolu (`apply_transitions` -> `task_status_events`/`task_projection`)
    eklediği için repo-pin'in bu yolu da fail-closed durdurduğunu AYRICA
    kilitliyoruz (o dosya bu görevin dosya kapsamı DIŞINDA, bkz. GOREV 3/4).

    MUTASYON KILIDI (3/3): `apply_transitions` çağrısı repo-pin kontrolünden
    ÖNCEYE alınırsa bu test KIRMIZI olmalı.
    """
    db_path = tmp_path / "repo-pin-transitions.db"
    settings = Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{db_path}",
        GITHUB_WEBHOOK_SECRET=_SECRET,
        DEMO_MODE=True,
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
    )
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(settings)
    with TestClient(app) as pin_client:
        _seed_task(pin_client.app.state.session_factory, "T-158", status="todo")

        payload = {
            "action": "closed",
            "issue": {"number": 158, "updated_at": "2026-07-25T09:00:00Z", "user": {"login": "esma"}},
            "repository": {"full_name": "baskasi/baska-repo"},
        }
        body = json.dumps(payload).encode()
        resp = pin_client.post(
            "/webhooks/github",
            content=body,
            headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "issues"},
        )
        assert resp.status_code == 202
        assert resp.json() == {"status": "ignored", "reason": "repo_not_pinned", "event": "issues"}

        with pin_client.app.state.session_factory() as session:
            assert session.query(EventRow).count() == 0
            assert session.query(TaskStatusEventRow).count() == 0
            assert (
                session.query(TaskProjectionRow).filter_by(task_id="T-158").one().status == "todo"
            )
