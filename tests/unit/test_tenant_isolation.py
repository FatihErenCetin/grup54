"""T-79 — çok-kiracılı repo seçimi: İZOLASYON testleri (#79'un en kritik parçası).

İki gerçek kiracı (REPO_A, REPO_B), her okuma ucu için AYRI test:
`/board`, `/events`+`/presence`, `/graph`, `/scope`, `/query`, `/radar`.
Her testte: kiracı A'nın isteği yalnız A'nın verisini görür (B'ninkini ASLA
GÖRMEZ) ve tersi. Ayrıca `?repo=` ile başkasının reposunu istemek 403 verir
(izinli sete karşı sunucu-taraflı doğrulama — istemciye güvenilmez) ve
oturumsuz istek DEMO repoya düşer (D-23 korunur).

MUTASYON KANITI (PR gövdesinde tablo halinde de raporlanır): geliştirme
sırasında her `repo_full_name` filtresi (BoardService/EventService/
GraphService/QueryService/RadarService'in TenantRegistry'de aldığı port
ayrımı + api/deps.py::get_tenant) TEK TEK kaldırılıp bu testlerin KIRMIZI
olduğu elle doğrulandı, sonra geri alındı.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from ensemble.api.auth_session import SESSION_COOKIE_NAME, sign_session
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.models import NormalizedEvent
from ensemble.store.models import (
    Base,
    EventRow,
    InstallationRow,
    TaskProjectionRow,
    UserRow,
    WatchedRepoRow,
)

REPO_A = "acme/repo-a"
REPO_B = "acme/repo-b"
REPO_C_YABANCI = "acme/repo-c-yabanci"  # ne A ne B izliyor — 403 kanıtı için
_SECRET = "isolation-test-secret"


def _fake_adapter_factory(settings):
    """`ensemble.tenancy.GitHubAdapter`'ın yerine geçer (monkeypatch) — GERÇEK
    GitHub App kimlik bilgisi olmadan her kiracının KENDİ, birbirinden
    AYIRT EDİLEBİLİR (aktör adı repoyu taşır) sahte event kümesiyle
    `RadarService` kurulmasını sağlar. `GitHubAdapter`'ın KENDİSİ hiç
    değişmedi — yalnız test bunu neyin inşa ettiğini kontrol ediyor."""
    owner_repo = f"{settings.GITHUB_REPO_OWNER}/{settings.GITHUB_REPO_NAME}"
    tag = owner_repo.replace("/", "-")
    events = [
        NormalizedEvent(
            id=f"commit:{tag}-1",
            type="commit",
            actor=f"actor-{tag}",
            branch=f"T-1-{tag}",
            files=["src/shared.py"],
            ts=datetime(2026, 7, 20, 9, 0, 0, tzinfo=timezone.utc),
            ref=f"sha-{tag}-1",
        ),
        NormalizedEvent(
            id=f"commit:{tag}-2",
            type="commit",
            actor=f"other-{tag}",
            branch=f"T-2-{tag}",
            files=["src/shared.py"],
            ts=datetime(2026, 7, 20, 9, 5, 0, tzinfo=timezone.utc),
            ref=f"sha-{tag}-2",
        ),
    ]
    return FakeGitHubAdapter(events=events)


def _seed_user(session, *, user_id: str, repo: str, installation_id: str) -> None:
    # Not: aralara `session.flush()` BİLEREK konuyor — SQLAlchemy'nin unit-of-
    # work INSERT sıralaması yalnızca `relationship()` üzerinden kurulan
    # bağımlılıkları göz önüne alır (ham `ForeignKey` kolonu tek başına
    # sıralamayı GARANTİLEMEZ); gerçek üretim akışında bu satırlar zaten AYRI
    # istekler/transaction'larda yazıldığı için bu sorun hiç YAŞANMAZ — burada
    # yalnızca test fixture'ının TEK oturumda üç tabloya birden yazması bunu
    # açığa çıkarıyor.
    now = datetime.utcnow()
    session.add(
        UserRow(
            id=user_id,
            email=f"{user_id}@example.com",
            password_hash="x",
            active_repo_full_name=repo,
            created_at=now,
        )
    )
    session.flush()
    session.add(
        InstallationRow(
            installation_id=installation_id,
            account_login=repo.split("/")[0],
            user_id=user_id,
            created_at=now,
        )
    )
    session.flush()
    session.add(
        WatchedRepoRow(
            user_id=user_id,
            repo_full_name=repo,
            installation_id=installation_id,
            created_at=now,
        )
    )
    session.flush()


def _seed_tenant_data(session, repo: str, task_id: str, task_title: str, event_actor: str) -> None:
    session.add(
        TaskProjectionRow(
            task_id=task_id,
            repo_full_name=repo,
            title=task_title,
            status="in_progress",
            seed_status="todo",
            updated_at=datetime.utcnow(),
        )
    )
    session.add(
        EventRow(
            id=f"commit:{repo}-seed",
            repo_full_name=repo,
            type="commit",
            actor=event_actor,
            branch=None,
            files=["src/x.py"],
            ts=datetime(2026, 7, 21, 10, 0, 0),
            ref=f"sha-{repo}",
        )
    )


_DEMO_ONLY_PRESENCE_HANDLE = "demo-repo-gercek-presence-sizinti-kaniti"


@pytest.fixture
def isolation_app(tmp_path, monkeypatch):
    monkeypatch.setattr("ensemble.tenancy.GitHubAdapter", _fake_adapter_factory)

    # T-79 mutasyon-yakalama sağlamlığı: bu makinede/CI'da `.harness/active/`
    # GERÇEKTEN boş olabilir — o zaman "NullHarnessPort yerine yanlışlıkla
    # FileHarnessPort kullanılsa bile presence testi YİNE `[]` görür ve
    # mutasyonu KAÇIRIR" riski var. `FileHarnessPort.read_active`'ı BİLEREK
    # sahte-dolu bir sonuca sabitliyoruz ki "demo reponun gerçek presence'ı
    # non-demo kiracıya hiç sızmadı" iddiası ortamdan BAĞIMSIZ, gerçekten
    # test edilsin.
    monkeypatch.setattr(
        "ensemble_shared.harness.FileHarnessPort.read_active",
        lambda self: [
            {
                "handle": _DEMO_ONLY_PRESENCE_HANDLE,
                "task_id": "T-DEMO",
                "module": "demo-module",
                # TAZE bir zaman damgası ŞART — `EventService.get_presence()`
                # kendi TTL/bayatlık filtresini (#60) UYGULAR; eski bir
                # damga NullHarnessPort'tan bağımsız olarak zaten elenir ve
                # mutasyonu (yanlış harness port) SESSİZCE MASKELERDİ.
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )

    db_path = tmp_path / "isolation.db"
    settings = Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{db_path}",
        AUTH_SESSION_SECRET=_SECRET,
    )
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver") as client:
        engine = app.state.session_factory.kw["bind"]
        Base.metadata.create_all(engine)

        with app.state.session_factory() as session:
            _seed_user(session, user_id="user-a", repo=REPO_A, installation_id="inst-a")
            _seed_user(session, user_id="user-b", repo=REPO_B, installation_id="inst-b")
            _seed_tenant_data(
                session, REPO_A, "T-100", "A'nın gizli görevi", "isolationactor-a-benzersiz"
            )
            _seed_tenant_data(
                session, REPO_B, "T-200", "B'nin gizli görevi", "isolationactor-b-benzersiz"
            )
            session.commit()

        token_a = sign_session(_SECRET, sub="user-a")
        token_b = sign_session(_SECRET, sub="user-b")
        yield app, client, token_a, token_b


def _as(client: TestClient, token: str) -> TestClient:
    client.cookies.set(SESSION_COOKIE_NAME, token)
    return client


def _anonymous(client: TestClient) -> TestClient:
    client.cookies.delete(SESSION_COOKIE_NAME)
    return client


# ---------------------------------------------------------------------------
# /board
# ---------------------------------------------------------------------------


def test_board_izolasyonu(isolation_app):
    _app, client, token_a, token_b = isolation_app

    resp_a = _as(client, token_a).get("/board")
    assert resp_a.status_code == 200
    ids_a = {card["task_id"] for card in resp_a.json()["cards"]}
    assert ids_a == {"T-100"}, f"A'nın board'unda B'nin görevi sızdı: {ids_a}"

    resp_b = _as(client, token_b).get("/board")
    assert resp_b.status_code == 200
    ids_b = {card["task_id"] for card in resp_b.json()["cards"]}
    assert ids_b == {"T-200"}, f"B'nin board'unda A'nın görevi sızdı: {ids_b}"


# ---------------------------------------------------------------------------
# /events + /presence
# ---------------------------------------------------------------------------


def test_events_izolasyonu(isolation_app):
    _app, client, token_a, token_b = isolation_app

    resp_a = _as(client, token_a).get("/events")
    assert resp_a.status_code == 200
    ids_a = {e["id"] for e in resp_a.json()["events"]}
    assert ids_a == {f"commit:{REPO_A}-seed"}, f"A'nın feed'inde B'nin event'i sızdı: {ids_a}"

    resp_b = _as(client, token_b).get("/events")
    assert resp_b.status_code == 200
    ids_b = {e["id"] for e in resp_b.json()["events"]}
    assert ids_b == {f"commit:{REPO_B}-seed"}, f"B'nin feed'inde A'nın event'i sızdı: {ids_b}"


def test_presence_izolasyonu_dogru_yapilandirilmamis_doner(isolation_app):
    """`.harness/active/` yalnız DEMO reponun yerel diskinde yaşar — gerçek
    (non-demo) kiracılar için NullHarnessPort HER ZAMAN boş döner. Bu, o
    dizinde gerçekten bir şey olsa bile (bu reponun kendi `.harness/active/`
    dosyaları) hiçbir kiracıya SIZMADIĞININ kanıtıdır."""
    _app, client, token_a, token_b = isolation_app

    resp_a = _as(client, token_a).get("/presence")
    assert resp_a.status_code == 200
    assert resp_a.json()["entries"] == []

    resp_b = _as(client, token_b).get("/presence")
    assert resp_b.status_code == 200
    assert resp_b.json()["entries"] == []


# ---------------------------------------------------------------------------
# /graph
# ---------------------------------------------------------------------------


def test_graph_izolasyonu(isolation_app):
    _app, client, token_a, token_b = isolation_app

    resp_a = _as(client, token_a).get("/graph")
    assert resp_a.status_code == 200
    actors_a = {n["id"] for n in resp_a.json()["nodes"] if n["type"] == "actor"}
    assert actors_a == {"isolationactor-a-benzersiz"}, f"A'nın grafiğinde B sızdı: {actors_a}"

    resp_b = _as(client, token_b).get("/graph")
    assert resp_b.status_code == 200
    actors_b = {n["id"] for n in resp_b.json()["nodes"] if n["type"] == "actor"}
    assert actors_b == {"isolationactor-b-benzersiz"}, f"B'nin grafiğinde A sızdı: {actors_b}"


# ---------------------------------------------------------------------------
# /scope
# ---------------------------------------------------------------------------


def test_scope_izolasyonu_gercek_repo_verisi_sizdirmaz(isolation_app):
    """Non-demo kiracılar için `.harness/scope/` yapılandırılmamıştır —
    dürüst 503 döner, grup54'ün KENDİ (bu repodaki gerçek) scope içeriği
    hiçbir zaman başka bir kiracıya sızmaz."""
    _app, client, token_a, token_b = isolation_app

    for token in (token_a, token_b):
        resp = _as(client, token).get("/scope/current")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "scope_unavailable"
        # grup54'ün kendi gerçek scope metninden bilinen bir ibare asla gövdede olmasın.
        assert "kanonik proje bağlamında" not in body["message"]


# ---------------------------------------------------------------------------
# /query
# ---------------------------------------------------------------------------


def test_query_izolasyonu(isolation_app):
    _app, client, token_a, token_b = isolation_app

    resp_a = _as(client, token_a).get(
        "/query", params={"q": "isolationactor-a-benzersiz nedir"}
    )
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["status"] == "answered"
    assert any(
        (isinstance(c, dict) and c.get("ref") == f"sha-{REPO_A}") for c in data_a["citations"]
    ), f"A'nın sorusu A'nın kendi event'ini kanıt göstermedi: {data_a}"

    # AYNI (A'ya özgü) soru B'ye sorulunca: B'nin corpus'unda bu kelime hiç
    # YOK — retrieval "en yakın" belgeyi (B'nin KENDİ event'i) döndürebilir
    # (RAG sezgiseli, isolation'la ilgisiz) ama YANITTA/KANITTA A'ya ait HİÇBİR
    # ref/metin GÖRÜNMEMELİDİR — asıl izolasyon iddiası budur.
    resp_b = _as(client, token_b).get(
        "/query", params={"q": "isolationactor-a-benzersiz nedir"}
    )
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    cited_refs_b = {
        c.get("ref") for c in data_b["citations"] if isinstance(c, dict)
    }
    assert f"sha-{REPO_A}" not in cited_refs_b, f"B, A'nın verisini gösterdi: {data_b}"
    assert "isolationactor-a" not in data_b["answer"], f"B'nin cevabında A'nın verisi sızdı: {data_b}"


# ---------------------------------------------------------------------------
# /radar
# ---------------------------------------------------------------------------


def test_radar_izolasyonu(isolation_app):
    _app, client, token_a, token_b = isolation_app

    resp_a = _as(client, token_a).get("/radar")
    assert resp_a.status_code == 200
    actors_a = {actor for d in resp_a.json()["detections"] for actor in d["actors"]}
    assert actors_a, "A'nın radar'ı hiç tespit üretmedi (fixture regresyonu olabilir)"
    assert all(REPO_B not in actor for actor in actors_a), f"A'nın radar'ında B sızdı: {actors_a}"

    resp_b = _as(client, token_b).get("/radar")
    assert resp_b.status_code == 200
    actors_b = {actor for d in resp_b.json()["detections"] for actor in d["actors"]}
    assert actors_b, "B'nin radar'ı hiç tespit üretmedi (fixture regresyonu olabilir)"
    assert all(REPO_A not in actor for actor in actors_b), f"B'nin radar'ında A sızdı: {actors_b}"

    # Ek kilit: iki kiracının GitHubAdapter'ı PAYLAŞILIRSA (mutasyon) her iki
    # aktör kümesi de repo adını taşımayan AYNI (örn. "actor-None-None" gibi)
    # jenerik değerlere düşebilir — yukarıdaki substring kontrolleri bu durumu
    # KAÇIRIR. Kümelerin birbirinden AYRIK olması bunu da yakalar.
    assert actors_a.isdisjoint(actors_b), (
        f"A ve B AYNI radar verisini paylaşıyor (GitHubAdapter kiracılar arasında "
        f"paylaşılmış olabilir): A={actors_a} B={actors_b}"
    )


# ---------------------------------------------------------------------------
# ?repo= — istemciye KÖRLEMESİNE güvenilmez, izinli sete karşı doğrulanır
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/board", "/events", "/graph", "/radar"])
def test_repo_parametresi_izinsiz_ise_403(isolation_app, path):
    _app, client, token_a, _token_b = isolation_app

    # A, B'nin reposunu ?repo= ile istiyor — A'nın watched_repos'unda YOK.
    resp = _as(client, token_a).get(path, params={"repo": REPO_B})
    assert resp.status_code == 403, f"{path}: izinsiz ?repo= 403 vermedi ({resp.status_code})"

    # Hiç kimsenin izlemediği bir repo da aynı şekilde reddedilir.
    resp2 = _as(client, token_a).get(path, params={"repo": REPO_C_YABANCI})
    assert resp2.status_code == 403


def test_repo_parametresi_izinliyse_kabul_edilir(isolation_app):
    """A kendi izlediği REPO_A'yı `?repo=` ile AÇIKÇA isteyebilir (aktif
    repo zaten bu olsa da) — izinli setin İÇİNDE olan bir istek reddedilmez."""
    _app, client, token_a, _token_b = isolation_app

    resp = _as(client, token_a).get("/board", params={"repo": REPO_A})
    assert resp.status_code == 200
    ids = {card["task_id"] for card in resp.json()["cards"]}
    assert ids == {"T-100"}


# ---------------------------------------------------------------------------
# Anonim istek — demo repoya düşer (D-23 korunur), giriş duvarı YOK
# ---------------------------------------------------------------------------


def test_anonim_istek_demo_repoya_duser_ve_baskasinin_reposunu_isteyemez(isolation_app):
    _app, client, _token_a, _token_b = isolation_app

    resp = _anonymous(client).get("/board")
    assert resp.status_code == 200
    # Demo repo bu testte yapılandırılmamış (GITHUB_REPO_OWNER/NAME yok) —
    # DEFAULT_REPO_FULL_NAME'e düşer; A/B'nin görevlerinden HİÇBİRİNİ görmez.
    ids = {card["task_id"] for card in resp.json()["cards"]}
    assert ids.isdisjoint({"T-100", "T-200"})

    # Oturumsuz istemci A'nın ya da B'nin reposunu ?repo= ile de İSTEYEMEZ.
    resp_a = _anonymous(client).get("/board", params={"repo": REPO_A})
    assert resp_a.status_code == 403
