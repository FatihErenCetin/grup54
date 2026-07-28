"""Kullanıcı girişi (#79 daraltılmış dilim) — router (routers/auth.py) uçtan
uca testleri.

TestClient GERÇEK create_app + lifespan üzerinden (webhook.py testleri
deseniyle aynı disiplin — bkz. test_webhook.py) — yalnız GitHub'a giden AĞ
ÇAĞRILARI (token exchange + /user, callback içinde) monkeypatch ile
sahtelenir; state/çerez/imza mantığının KENDİSİ gerçek kod yolundan geçer.

NOT: `base_url="https://testserver"` BİLEREK — çerezler `Secure` bayrağıyla
kuruluyor (kontrat, #79 brifingi) ve `http://` şemasında `http.cookiejar`
(httpx'in altındaki katman) Secure çerezi asla geri GÖNDERMEZ (yalnız saklar) —
ölçüldü: varsayılan `http://testserver` ile state/session çerezleri hiç geri
gelmiyordu, testler sessizce YANLIŞ senaryoyu (çerezsiz istek) test ediyordu.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ensemble.api.auth_session import SESSION_COOKIE_NAME, STATE_COOKIE_NAME, sign_session, verify_session
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.store.models import Base

_AUTH_SETTINGS = {
    "GITHUB_OAUTH_CLIENT_ID": "client-123",
    "GITHUB_OAUTH_CLIENT_SECRET": "secret-abc",
    "AUTH_SESSION_SECRET": "session-secret-xyz",
}


def _client(**overrides) -> TestClient:
    settings = Settings(_env_file=None, **overrides)
    return TestClient(create_app(settings), base_url="https://testserver")


# --- /auth/config ---


def test_config_sirlar_yokken_disabled():
    with _client() as client:
        resp = client.get("/auth/config")
    assert resp.status_code == 200
    # T-294: email_enabled AUTH_SESSION_SECRET'e bağlı (GitHub'dan bağımsız) —
    # burada o da yok, ikisi de False.
    assert resp.json() == {"enabled": False, "email_enabled": False}


def test_config_ucu_de_doluyken_enabled():
    with _client(**_AUTH_SETTINGS) as client:
        resp = client.get("/auth/config")
    assert resp.json() == {"enabled": True, "email_enabled": True}


@pytest.mark.parametrize(
    "missing", ["GITHUB_OAUTH_CLIENT_ID", "GITHUB_OAUTH_CLIENT_SECRET", "AUTH_SESSION_SECRET"]
)
def test_config_tek_biri_eksikse_disabled(missing):
    values = {k: v for k, v in _AUTH_SETTINGS.items() if k != missing}
    with _client(**values) as client:
        resp = client.get("/auth/config")
    # T-294: email_enabled yalnız AUTH_SESSION_SECRET'e bakar — GITHUB_OAUTH_*
    # eksikken bile (AUTH_SESSION_SECRET doluysa) email kaydı AÇIK olmalı;
    # bu ikisinin BAĞIMSIZ kapılar olduğunun asıl kanıtı.
    assert resp.json() == {
        "enabled": False,
        "email_enabled": missing != "AUTH_SESSION_SECRET",
    }


# --- /auth/login ---


def test_login_yapilandirilmamissa_503():
    with _client() as client:
        resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 503


def test_login_yapilandirilmislarsa_githuba_yonlendirir_ve_state_cerezi_koyar():
    with _client(**_AUTH_SETTINGS) as client:
        resp = client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith("https://github.com/login/oauth/authorize?")
        query = parse_qs(urlparse(location).query)
        assert query["client_id"] == ["client-123"]
        assert "state" in query
        assert client.cookies.get(STATE_COOKIE_NAME) == query["state"][0]


# --- /auth/callback ---


def test_callback_yapilandirilmamissa_503():
    with _client() as client:
        resp = client.get("/auth/callback?code=x&state=y", follow_redirects=False)
    assert resp.status_code == 503


def test_callback_github_hatasi_durustce_ele_alinir_oturum_acilmaz():
    """Kullanıcı GitHub'da yetkilendirmeyi reddettiğinde GitHub `?error=...`
    ile callback'e döner — 500'e düşmeden, oturum açmadan sessizce döner."""
    with _client(**_AUTH_SETTINGS) as client:
        resp = client.get(
            "/auth/callback?error=access_denied&error_description=kullanici+reddetti",
            follow_redirects=False,
        )
    assert resp.status_code == 302
    # Varsayilan artik MUTLAK bir URL (#258) - goreli "/radar" DEGIL; bkz.
    # config.py::Settings._validate_auth_post_login_url_absolute.
    assert resp.headers["location"] == "http://localhost:5173/radar"
    assert SESSION_COOKIE_NAME not in resp.cookies


def test_callback_state_cerezi_yoksa_400():
    with _client(**_AUTH_SETTINGS) as client:
        resp = client.get("/auth/callback?code=abc&state=whatever", follow_redirects=False)
    assert resp.status_code == 400


def test_callback_state_uyusmazliginda_400():
    with _client(**_AUTH_SETTINGS) as client:
        client.get("/auth/login", follow_redirects=False)  # state çerezini koyar
        resp = client.get("/auth/callback?code=abc&state=baska-bir-deger", follow_redirects=False)
    assert resp.status_code == 400


def test_callback_mutlu_yol_oturum_cerezi_kurulur_ve_yonlendirir(monkeypatch, tmp_path):
    """T-79: callback artık (`identities` üzerinden get-or-create) `users`'a
    yazıyor — bu yüzden bu TEK test (dosyadaki diğerlerinin aksine) kendi
    `tmp_path` SQLite'ını kurar (`test_auth_email.py` ile AYNI desen);
    varsayılan `_client()` gerçek repo kökü `ensemble.db`'sine düşer ve onu
    override etmemek gerçek geliştirici veritabanını kirletirdi."""
    monkeypatch.setattr(
        "ensemble.api.routers.auth.exchange_code_for_token",
        lambda settings, *, code, redirect_uri: "gho_faketoken",
    )
    monkeypatch.setattr(
        "ensemble.api.routers.auth.fetch_github_user",
        lambda access_token, **_kwargs: ("esma6", "https://avatars.example/esma6.png", "999111"),
    )
    # Mutlak URL - production'daki gercek deger (#258): goreli "/radar"
    # artik Settings acilista reddediyor (bkz. test_config.py).
    db_path = tmp_path / "callback.db"
    settings = Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{db_path}",
        **{**_AUTH_SETTINGS, "AUTH_POST_LOGIN_URL": "https://app.example.com/radar"},
    )
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver") as client:
        engine = app.state.session_factory.kw["bind"]
        Base.metadata.create_all(engine)

        client.get("/auth/login", follow_redirects=False)
        state = client.cookies.get(STATE_COOKIE_NAME)

        resp = client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"] == "https://app.example.com/radar"
        session_cookie = client.cookies.get(SESSION_COOKIE_NAME)
        assert session_cookie is not None
        payload = verify_session("session-secret-xyz", session_cookie)
        assert payload["handle"] == "esma6"
        assert payload["avatar_url"] == "https://avatars.example/esma6.png"
        # T-79: get-or-create bir `users.id` açtı — session artık `sub` da taşır.
        assert payload["sub"]
        # state çerezi tek kullanımlık — geri gelen yanıtta temizlenmiş olmalı.
        assert client.cookies.get(STATE_COOKIE_NAME) is None

        with app.state.session_factory() as session:
            from ensemble.store.models import IdentityRow, UserRow

            user = session.query(UserRow).filter_by(github_handle="esma6").one()
            assert user.id == payload["sub"]
            identity = session.query(IdentityRow).filter_by(provider_user_id="999111").one()
            assert identity.user_id == user.id

        # İkinci giriş AYNI GitHub kimliği için YENİ bir `users` satırı AÇMAZ.
        resp2 = client.get("/auth/login", follow_redirects=False)
        state2 = client.cookies.get(STATE_COOKIE_NAME)
        resp2 = client.get(f"/auth/callback?code=abc2&state={state2}", follow_redirects=False)
        assert resp2.status_code == 302
        payload2 = verify_session("session-secret-xyz", client.cookies.get(SESSION_COOKIE_NAME))
        assert payload2["sub"] == payload["sub"]
        with app.state.session_factory() as session:
            from ensemble.store.models import UserRow

            assert session.query(UserRow).filter_by(github_handle="esma6").count() == 1


def test_callback_goreli_yonlendirme_ayari_sunucu_ayaga_kalkmadan_reddedilir():
    """#258 kilidi: yanlış yapılandırma (göreli AUTH_POST_LOGIN_URL) canlı bir
    sunucuda 302 + sessiz 404 üretemez — Settings inşası sırasında (uygulama
    ayağa kalkmadan) patlar. `_client()` burada BİLEREK TestClient'a hiç
    girmiyor: regresyon `RedirectResponse`'a değil, `Settings`'e — yanlış
    katmanda test edilirse (örn. router'ı monkeypatch'leyip yalnız location
    header'ına bakarsak) validator kaldırılsa bile bu test yeşil kalırdı."""
    with pytest.raises(ValidationError, match="MUTLAK bir URL"):
        _client(**_AUTH_SETTINGS, AUTH_POST_LOGIN_URL="/radar")


# --- /auth/me ---


def test_me_cerez_yoksa_401():
    with _client(**_AUTH_SETTINGS) as client:
        resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_cerez_imzasi_bozukken_401():
    with _client(**_AUTH_SETTINGS) as client:
        client.cookies.set(SESSION_COOKIE_NAME, "bozuk.deger")
        resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_gecerli_cerezle_200():
    token = sign_session("session-secret-xyz", handle="fatih", avatar_url=None)
    with _client(**_AUTH_SETTINGS) as client:
        client.cookies.set(SESSION_COOKIE_NAME, token)
        resp = client.get("/auth/me")
    assert resp.status_code == 200
    # T-294: AuthUserResponse'a `email` eklendi (GitHub oturumunda None).
    assert resp.json() == {"handle": "fatih", "avatar_url": None, "email": None}


def test_me_auth_devre_disiyken_gecerli_cerezle_bile_401():
    """AUTH_SESSION_SECRET yoksa hiçbir çerez asla doğrulanamaz (fail-closed)."""
    token = sign_session("baska-secret", handle="fatih", avatar_url=None)
    with _client() as client:  # AUTH_SESSION_SECRET yok
        client.cookies.set(SESSION_COOKIE_NAME, token)
        resp = client.get("/auth/me")
    assert resp.status_code == 401


# --- /auth/logout ---


def test_logout_oturum_yokken_bile_204():
    with _client(**_AUTH_SETTINGS) as client:
        resp = client.post("/auth/logout")
    assert resp.status_code == 204


def test_logout_cerezi_siler():
    """Sunucunun gerçekten silme talimatı (Max-Age=0) gönderdiğini Set-Cookie
    başlığından doğrular — TestClient'ın httpx tabanlı çerez kavanozu Max-Age=0'ı
    tarayıcılar gibi anında UYGULAMIYOR (ölçüldü: `client.cookies` silme
    sonrası bile eski değeri taşımaya devam ediyor), bu yüzden asıl kanıt
    başlığın kendisidir — bir tarayıcı bu başlığı görünce çerezi anında siler."""
    with _client(**_AUTH_SETTINGS) as client:
        resp = client.post("/auth/logout")
    assert resp.status_code == 204
    set_cookie = resp.headers.get("set-cookie", "")
    assert set_cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "Max-Age=0" in set_cookie
