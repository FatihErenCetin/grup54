"""Hosted demo IP/rate cap testleri (#63 — api/rate_limit.py + app.py wiring).

Anti-tautoloji: middleware ASGI katmanında yalnız path/method'a bakar; /query
ve /scope/check'in ALT katmanı hafif fake servislerle override edilir ki
assertion'lar TEK BİR şeyi (rate-limit kararı) ölçsün — eksik `.harness/`
gibi downstream hatalarla karışmasın (test_query_router.py deseninin aynısı).
`sleep` YOK — WindowCounter testlerinde saat enjekte edilir.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from starlette.requests import Request

from ensemble.api.deps import get_query_service, get_scope_service
from ensemble.api.rate_limit import WindowCounter, client_ip
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.models import QueryResult, ScopeVerdict
from ensemble.store.engine import get_engine
from ensemble.store.models import Base


class _FakeQueryService:
    def ask(self, question: str) -> QueryResult:
        return QueryResult(
            answer="ok",
            citations=[],
            as_of=datetime.now(timezone.utc),
            last_commit="deadbeef",
            confidence="low",
            status="not_found",
            searched=[],
            nearest=[],
        )


class _FakeScopeService:
    def check_scope(self, ref: str) -> ScopeVerdict:
        return ScopeVerdict(ref=ref, verdict="in_scope", confidence=0.9, evidence="ok")


def _settings(tmp_path, **overrides) -> Settings:
    db_path = tmp_path / "demo-rate.db"
    defaults: dict = dict(
        _env_file=None,
        DEMO_MODE=True,
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
        DATABASE_URL=f"sqlite:///{db_path}",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _client(settings: Settings) -> TestClient:
    # /board TaskProjectionRow tablosunu okuyor - test 7 icin onceden kur
    # (test_board_router.py deseni). DEMO_MODE'un rate-limit'iyle alakasiz,
    # yalniz "/board hala 200" iddiasini gercek kilmak icin.
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(settings)
    app.dependency_overrides[get_query_service] = _FakeQueryService
    app.dependency_overrides[get_scope_service] = _FakeScopeService
    return TestClient(app)


# --- 1. DEMO_MODE kapaliyken limit yok ---


def test_demo_kapali_iken_limit_yok(tmp_path):
    settings = _settings(tmp_path, DEMO_MODE=False, GITHUB_REPO_OWNER=None, GITHUB_REPO_NAME=None)
    with _client(settings) as client:
        # limitin (varsayilan DEMO_AI_RATE_LIMIT=10) kati kadar istek - hicbiri 429 degil
        responses = [client.get("/query", params={"q": "test"}) for _ in range(30)]
    assert all(r.status_code == 200 for r in responses)


# --- 2. AI yolu IP basina limitte 429 doner ---


def test_ai_yolu_ip_basina_limitte_429_doner(tmp_path):
    settings = _settings(tmp_path, DEMO_AI_RATE_LIMIT=2, DEMO_AI_GLOBAL_LIMIT=100)
    with _client(settings) as client:
        r1 = client.get("/query", params={"q": "bir"})
        r2 = client.get("/query", params={"q": "iki"})
        r3 = client.get("/query", params={"q": "uc"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    body = r3.json()
    assert body["error"] == "demo_rate_limited"
    assert body["status"] == 429
    assert int(r3.headers["retry-after"]) > 0


# --- 3. Farkli IP ayri kovaya duser ---


def test_farkli_ip_ayri_kovaya_duser(tmp_path):
    settings = _settings(tmp_path, DEMO_AI_RATE_LIMIT=1, DEMO_AI_GLOBAL_LIMIT=100)
    with _client(settings) as client:
        r_a1 = client.get("/query", params={"q": "a"})
        r_a2 = client.get("/query", params={"q": "a-tekrar"})
        r_b1 = client.get(
            "/query", params={"q": "b"}, headers={"Fly-Client-IP": "9.9.9.9"}
        )

    assert r_a1.status_code == 200
    assert r_a2.status_code == 429  # ayni IP (varsayilan test istemcisi) limiti doldurdu
    assert r_b1.status_code == 200  # farkli IP, ayri kova


# --- 4. Global tavan farkli IP'lerde de kapatir ---


def test_global_tavan_farkli_iplerde_de_kapatir(tmp_path):
    settings = _settings(tmp_path, DEMO_AI_RATE_LIMIT=100, DEMO_AI_GLOBAL_LIMIT=2)
    with _client(settings) as client:
        r1 = client.get("/query", params={"q": "1"}, headers={"Fly-Client-IP": "1.1.1.1"})
        r2 = client.get("/query", params={"q": "2"}, headers={"Fly-Client-IP": "2.2.2.2"})
        r3 = client.get("/query", params={"q": "3"}, headers={"Fly-Client-IP": "3.3.3.3"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429  # global tavan (2) uc farkli IP'ye ragmen kapatti


# --- 5. client_ip basligi onceligi (saf birim) ---


def _make_request(headers: list[tuple[bytes, bytes]], client: tuple[str, int] | None) -> Request:
    scope = {
        "type": "http",
        "headers": headers,
        "client": client,
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "http_version": "1.1",
        "scheme": "http",
        "server": ("test", 80),
    }
    return Request(scope)


def test_client_ip_baslik_onceligi():
    # Fly-Client-IP en yuksek oncelik
    req = _make_request(
        [(b"fly-client-ip", b"1.1.1.1"), (b"x-forwarded-for", b"2.2.2.2")],
        ("3.3.3.3", 1234),
    )
    assert client_ip(req) == "1.1.1.1"

    # Fly-Client-IP yoksa X-Forwarded-For'un ILK kaydi
    req = _make_request([(b"x-forwarded-for", b"4.4.4.4, 5.5.5.5")], ("3.3.3.3", 1234))
    assert client_ip(req) == "4.4.4.4"

    # ikisi de yoksa request.client.host
    req = _make_request([], ("3.3.3.3", 1234))
    assert client_ip(req) == "3.3.3.3"

    # hicbiri yoksa "unknown"
    req = _make_request([], None)
    assert client_ip(req) == "unknown"


# --- 6. /health hic limitlenmez ---


def test_health_hic_limitlenmez(tmp_path):
    settings = _settings(tmp_path, DEMO_RATE_LIMIT=1, DEMO_AI_RATE_LIMIT=1, DEMO_AI_GLOBAL_LIMIT=1)
    with _client(settings) as client:
        responses = [client.get("/health") for _ in range(20)]
    assert all(r.status_code == 200 for r in responses)


# --- 7. Genel kova AI kovasindan bagimsiz ---


def test_genel_kova_ai_kovasindan_bagimsiz(tmp_path):
    settings = _settings(tmp_path, DEMO_AI_RATE_LIMIT=1, DEMO_AI_GLOBAL_LIMIT=1, DEMO_RATE_LIMIT=100)
    with _client(settings) as client:
        client.get("/query", params={"q": "once"})
        blocked = client.get("/query", params={"q": "tekrar"})
        board_resp = client.get("/board")
        radar_resp = client.get("/radar")

    assert blocked.status_code == 429  # AI kovasi tukendi
    assert board_resp.status_code == 200  # genel kova ayri - hala calisiyor
    assert radar_resp.status_code == 200


# --- 8. 429 cevabi CORS basligi tasir (middleware sirasi regresyon kilidi) ---


def test_429_cevabi_cors_basligi_tasir(tmp_path):
    allowed_origin = "http://localhost:5173"
    settings = _settings(
        tmp_path, DEMO_AI_RATE_LIMIT=1, DEMO_AI_GLOBAL_LIMIT=100, CORS_ORIGINS=[allowed_origin]
    )
    with _client(settings) as client:
        client.get("/query", params={"q": "once"}, headers={"Origin": allowed_origin})
        blocked = client.get(
            "/query", params={"q": "tekrar"}, headers={"Origin": allowed_origin}
        )

    assert blocked.status_code == 429
    assert blocked.headers.get("access-control-allow-origin") == allowed_origin


# --- 9. Pencere kayinca yeniden izin verilir (WindowCounter, saf) ---


def test_pencere_kayinca_yeniden_izin_verilir():
    now = [0.0]
    counter = WindowCounter(10, time_fn=lambda: now[0])

    allowed, _ = counter.allow("k", 1)
    assert allowed

    allowed, retry_after = counter.allow("k", 1)
    assert not allowed
    assert 0 < retry_after <= 10

    now[0] = 5.0
    _, retry_after_later = counter.allow("k", 1)
    assert retry_after_later < retry_after  # pencere icinde azaliyor

    now[0] = 10.0001
    allowed, _ = counter.allow("k", 1)
    assert allowed  # pencere kaydi, tekrar izin verildi


# --- 10. Anahtar sayisi sinirlanir (bellek DoS korumasi) ---


def test_anahtar_sayisi_sinirlanir():
    counter = WindowCounter(60, max_keys=100, time_fn=lambda: 0.0)
    for i in range(10_000):
        counter.allow(f"ip-{i}", 1000)
    assert len(counter) <= 100


# --- 11b. G6: genel kova global tavani IP rotasyonuna karsi kapatir ---


def test_genel_kova_global_tavan_ip_rotasyonuna_karsi_kapatir(tmp_path):
    """G6 regresyon kilidi: /radar (Gemini judge+embeddings cagiriyor, Ek F)
    BILEREK genel kovada kaliyor (AI kovasina tasinmiyor - kendi 10 sn'lik
    poll'u AI kovasinin cok daha siki butcesini paylasirdi). ESKIDEN genel
    kovanin yalniz IP-basina sayaci vardi -> sahte Fly-Client-IP rotasyonuyla
    (her istek farkli IP) bu sinirsizca asilirdi (olcum: 2000 istek/2000
    uydurma IP -> 200=2000, 429=0).

    DEMO_RATE_LIMIT=20 (IP basina, pratikte hic dolmaz - her sahte IP yalniz
    1 istek atiyor), DEMO_AI_RATE_LIMIT=10, DEMO_AI_GLOBAL_LIMIT=1 ->
    turetilen genel-kova global tavani = round(20 * 1 / 10) = 2. Uc FARKLI
    IP'den tek's er istek: ilk ikisi genel-kova GLOBAL sayacini doldurur,
    ucuncusu (farkli IP olmasina ragmen) 429 doner - fix geri alinirsa
    (rate_limit.py'deki global kontrol kaldirilirsa) bu test kirilir."""
    settings = _settings(
        tmp_path, DEMO_RATE_LIMIT=20, DEMO_AI_RATE_LIMIT=10, DEMO_AI_GLOBAL_LIMIT=1
    )
    with _client(settings) as client:
        r1 = client.get("/radar", headers={"Fly-Client-IP": "10.0.0.1"})
        r2 = client.get("/radar", headers={"Fly-Client-IP": "10.0.0.2"})
        r3 = client.get("/radar", headers={"Fly-Client-IP": "10.0.0.3"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429  # farkli IP ama global tavan (2) doldu
    body = r3.json()
    assert body["error"] == "demo_rate_limited"
    assert int(r3.headers["retry-after"]) > 0


def test_genel_kova_global_tavan_varsayilan_oranla_turetilir(tmp_path):
    """Turetme formulunun (yeni env EKLEMEDEN, mevcut DEMO_* degerlerinden)
    dogru calistigini varsayilan degerlerle kilitler: DEMO_RATE_LIMIT=120,
    DEMO_AI_RATE_LIMIT=10, DEMO_AI_GLOBAL_LIMIT=60 -> 120*60/10=720."""
    from ensemble.api.rate_limit import DemoRateLimitMiddleware

    settings = _settings(tmp_path)  # tum DEMO_* varsayilanlarda
    middleware = DemoRateLimitMiddleware(app=lambda *a, **k: None, settings=settings)
    assert middleware._general_global_limit == 720


# --- 11. Webhook POST'u limitlenmez (GET-disi muafiyet) ---


def test_webhook_postu_limitlenmez(tmp_path):
    secret = "test-secret"
    settings = _settings(tmp_path, DEMO_RATE_LIMIT=1, GITHUB_WEBHOOK_SECRET=secret)
    body = json.dumps({"ref": "refs/heads/main", "commits": []}).encode()
    bad_signature = "sha256=" + "0" * 64

    with _client(settings) as client:
        responses = [
            client.post(
                "/webhooks/github",
                content=body,
                headers={"X-Hub-Signature-256": bad_signature, "X-GitHub-Event": "push"},
            )
            for _ in range(5)
        ]

    # imza gecersiz oldugu icin hepsi 401 - ama KRITIK olan: hicbiri 429 degil
    # (POST muafiyeti calismasaydi 2.'den itibaren 429 gorurduk, limit=1).
    assert all(r.status_code == 401 for r in responses)
