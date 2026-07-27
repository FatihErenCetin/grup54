"""Email + parola üyelik (T-294/D-57) — `POST /auth/register` + `POST
/auth/login` uçtan uca testleri. GitHub OAuth akışının testi
`test_auth_router.py`'de kalıyor; bu dosya YALNIZCA email dilimini kapsar.

DB izolasyonu: `test_board_router.py` ile AYNI desen — her test kendi
`tmp_path` SQLite dosyasını kullanır (varsayılan `DATABASE_URL` GERÇEK repo
kökü `ensemble.db`'sine düşer; register/login DB'YE YAZDIĞI için bunu
override ETMEMEK gerçek geliştirici veritabanını kirletirdi).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from ensemble.api.auth_session import SESSION_COOKIE_NAME, verify_session
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.store.models import Base

_AUTH_SETTINGS = {"AUTH_SESSION_SECRET": "session-secret-xyz"}


def _client(db_path, **overrides) -> TestClient:
    """`auth.py::_auth_rate_counter` SÜREÇ/MODÜL SEVİYESİNDE bir tekil —
    tüm testler arasında PAYLAŞILIR (bkz. o modüldeki tanım). Testler
    birbirini rate-limit'e düşürmesin diye her istemciye `db_path`'ten
    türetilen BENZERSİZ bir `X-Forwarded-For` verilir — `client_ip()`
    (rate_limit.py) bunu gerçek IP'den önce okur, böylece her test kendi
    izole "IP kovasında" kalır (yalnızca RATE-LIMIT testi kasıtlı olarak
    aynı istemciden tekrar tekrar istek atar)."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{db_path}",
        **{**_AUTH_SETTINGS, **overrides},
    )
    app = create_app(settings)
    fake_ip = f"10.294.0.0-{db_path}"
    client = TestClient(app, base_url="https://testserver", headers={"X-Forwarded-For": fake_ip})
    client.__enter__()
    engine = app.state.session_factory.kw["bind"]
    Base.metadata.create_all(engine)
    return client


# --- /auth/config email_enabled alanı ---


def test_config_email_enabled_secret_varken_true(tmp_path):
    client = _client(tmp_path / "a.db")
    try:
        resp = client.get("/auth/config")
        assert resp.json()["email_enabled"] is True
    finally:
        client.__exit__(None, None, None)


def test_config_email_enabled_secret_yokken_false(tmp_path):
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{tmp_path / 'b.db'}")
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        assert client.get("/auth/config").json()["email_enabled"] is False


# --- /auth/register ---


def test_register_yapilandirilmamissa_503(tmp_path):
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{tmp_path / 'c.db'}")
    headers = {"X-Forwarded-For": "10.294.0.0-c"}
    with TestClient(create_app(settings), base_url="https://testserver", headers=headers) as client:
        resp = client.post("/auth/register", json={"email": "a@x.com", "password": "sifre1234"})
    assert resp.status_code == 503


def test_register_basarili_201_ve_cerez_kurar(tmp_path):
    client = _client(tmp_path / "d.db")
    try:
        resp = client.post("/auth/register", json={"email": "Ali@X.com", "password": "sifre1234"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "ali@x.com"  # normalize edilmiş
        assert body["handle"] is None
        cookie = client.cookies.get(SESSION_COOKIE_NAME)
        assert cookie is not None
        payload = verify_session("session-secret-xyz", cookie)
        assert payload["email"] == "ali@x.com"
        assert "sub" in payload and payload["sub"]
    finally:
        client.__exit__(None, None, None)


def test_register_ayni_email_ikinci_kez_409(tmp_path):
    client = _client(tmp_path / "e.db")
    try:
        client.post("/auth/register", json={"email": "ali@x.com", "password": "sifre1234"})
        resp = client.post("/auth/register", json={"email": "ali@x.com", "password": "baskasifre1"})
        assert resp.status_code == 409
    finally:
        client.__exit__(None, None, None)


def test_register_normalize_edilmis_email_de_cakisir(tmp_path):
    """#294 brifingi madde 2'nin doğrudan kanıtı: `Ali@X.com` ile
    `ali@x.com` AYNI hesaba düşmeli — ikinci istek 409 almalı, çift hesap
    AÇILMAMALI."""
    client = _client(tmp_path / "f.db")
    try:
        r1 = client.post("/auth/register", json={"email": "Ali@X.com", "password": "sifre1234"})
        r2 = client.post("/auth/register", json={"email": "ali@x.com", "password": "baskasifre1"})
        assert r1.status_code == 201
        assert r2.status_code == 409
    finally:
        client.__exit__(None, None, None)


@pytest.mark.parametrize("password", ["kisa", "a" * 129])
def test_register_parola_politikasi_disinda_422(tmp_path, password):
    client = _client(tmp_path / f"g-{len(password)}.db")
    try:
        resp = client.post("/auth/register", json={"email": "a@x.com", "password": password})
        assert resp.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_register_gecersiz_email_422(tmp_path):
    client = _client(tmp_path / "h.db")
    try:
        resp = client.post("/auth/register", json={"email": "gecersiz-email", "password": "sifre1234"})
        assert resp.status_code == 422
    finally:
        client.__exit__(None, None, None)


# --- /auth/login ---


def test_login_yapilandirilmamissa_503(tmp_path):
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{tmp_path / 'i.db'}")
    headers = {"X-Forwarded-For": "10.294.0.0-i"}
    with TestClient(create_app(settings), base_url="https://testserver", headers=headers) as client:
        resp = client.post("/auth/login", json={"email": "a@x.com", "password": "sifre1234"})
    assert resp.status_code == 503


def test_login_basarili_200_ve_cerez_kurar(tmp_path):
    client = _client(tmp_path / "j.db")
    try:
        client.post("/auth/register", json={"email": "ali@x.com", "password": "dogru-sifre-1"})
        client.cookies.clear()

        resp = client.post("/auth/login", json={"email": "ali@x.com", "password": "dogru-sifre-1"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "ali@x.com"
        assert client.cookies.get(SESSION_COOKIE_NAME) is not None
    finally:
        client.__exit__(None, None, None)


def test_login_normalize_edilmis_email_ile_de_calisir(tmp_path):
    client = _client(tmp_path / "k.db")
    try:
        client.post("/auth/register", json={"email": "ali@x.com", "password": "dogru-sifre-1"})
        client.cookies.clear()

        resp = client.post("/auth/login", json={"email": " Ali@X.com ", "password": "dogru-sifre-1"})
        assert resp.status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_login_yanlis_parola_401_genel_mesaj(tmp_path):
    client = _client(tmp_path / "l.db")
    try:
        client.post("/auth/register", json={"email": "ali@x.com", "password": "dogru-sifre-1"})
        client.cookies.clear()

        resp = client.post("/auth/login", json={"email": "ali@x.com", "password": "yanlis-sifre"})
        assert resp.status_code == 401
        assert "kayıtlı değil" not in resp.json()["message"].lower()
    finally:
        client.__exit__(None, None, None)


def test_login_olmayan_email_de_ayni_genel_401_verir(tmp_path):
    """Kullanıcı-sayımı savunması: var olmayan bir email ile var olan ama
    yanlış parolalı bir email AYNI hata gövdesini dönmeli — hangisinin
    "kayıtlı" olduğu ayırt edilemez olmalı."""
    client = _client(tmp_path / "m.db")
    try:
        client.post("/auth/register", json={"email": "var-olan@x.com", "password": "dogru-sifre-1"})
        client.cookies.clear()

        resp_yok = client.post(
            "/auth/login", json={"email": "hic-yok@x.com", "password": "her-hangi-bir-sey"}
        )
        resp_yanlis_sifre = client.post(
            "/auth/login", json={"email": "var-olan@x.com", "password": "yanlis-sifre"}
        )
        assert resp_yok.status_code == resp_yanlis_sifre.status_code == 401
        assert resp_yok.json() == resp_yanlis_sifre.json()
    finally:
        client.__exit__(None, None, None)


def test_login_zamanlama_var_olan_ve_olmayan_email_arasinda_kabaca_esit(tmp_path):
    """#294 brifingi madde 6'nın uçtan-uca (yalnız `credentials.py` birim
    seviyesinde değil, gerçek `/auth/login` isteği üzerinden) kanıtı.
    Gürültüye dayanıklı olsun diye MUTLAK bir eşik yerine iki ortalamanın
    aynı BÜYÜKLÜK MERTEBESİNDE (10x içinde) kaldığı kontrol edilir — asıl
    yakalanması gereken regresyon ("var olmayan email anında 401 döner, iş
    yapmaz") bunun çok üstünde bir fark üretir."""
    client = _client(tmp_path / "n.db")
    try:
        client.post(
            "/auth/register",
            json={"email": "var-olan@x.com", "password": "dogru-sifre-1"},
            headers={"X-Forwarded-For": "10.294.0.0-n-register"},
        )
        client.cookies.clear()

        # Kaba kuvvet limiti (_AUTH_RATE_LIMIT=5/60sn, register+login PAYLAŞIMLI)
        # bu testin 6 login çağrısını YARIDA keserdi (ölçümü bozardı) — her
        # çağrı BENZERSİZ bir X-Forwarded-For ile kendi izole kovasında kalır;
        # bu testin amacı rate-limit'i değil zamanlama simetrisini ölçmek.
        _sayac = iter(range(1_000_000))

        def _sure(email: str) -> float:
            fake_ip = f"10.294.0.0-n-{next(_sayac)}"
            baslangic = time.perf_counter()
            client.post(
                "/auth/login",
                json={"email": email, "password": "yanlis-sifre-xxxx"},
                headers={"X-Forwarded-For": fake_ip},
            )
            return time.perf_counter() - baslangic

        var_olan_sureler = [_sure("var-olan@x.com") for _ in range(3)]
        yok_sureler = [_sure("hic-yok@x.com") for _ in range(3)]

        ort_var = sum(var_olan_sureler) / len(var_olan_sureler)
        ort_yok = sum(yok_sureler) / len(yok_sureler)

        oran = max(ort_var, ort_yok) / max(min(ort_var, ort_yok), 1e-9)
        assert oran < 10, (
            f"var-olan ({ort_var:.4f}s) ile yok ({ort_yok:.4f}s) arasındaki "
            f"süre oranı ({oran:.1f}x) çok büyük — sahte-hash dalı atlanmış olabilir"
        )
    finally:
        client.__exit__(None, None, None)


def test_login_uzun_parola_hash_lenmeden_401_ile_erken_reddedilir(tmp_path):
    client = _client(tmp_path / "o.db")
    try:
        resp = client.post(
            "/auth/login", json={"email": "a@x.com", "password": "a" * 5000}
        )
        assert resp.status_code == 401
    finally:
        client.__exit__(None, None, None)


# --- /auth/me + /auth/logout email oturumuyla ---


def test_me_email_oturumuyla_calisir(tmp_path):
    client = _client(tmp_path / "p.db")
    try:
        client.post("/auth/register", json={"email": "ali@x.com", "password": "dogru-sifre-1"})
        resp = client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json() == {"handle": None, "avatar_url": None, "email": "ali@x.com"}
    finally:
        client.__exit__(None, None, None)


def test_logout_email_oturumunu_da_siler(tmp_path):
    client = _client(tmp_path / "q.db")
    try:
        client.post("/auth/register", json={"email": "ali@x.com", "password": "dogru-sifre-1"})
        resp = client.post("/auth/logout")
        assert resp.status_code == 204
        assert client.get("/auth/me").status_code == 401
    finally:
        client.__exit__(None, None, None)


# --- Kaba kuvvet koruması (#294 brifingi madde 7) ---


def test_login_rate_limit_asilinca_429_ve_retry_after(tmp_path):
    client = _client(tmp_path / "r.db")
    try:
        # Modül-seviyesi _auth_rate_counter TÜM testler arasında PAYLAŞILIR
        # (aynı süreç) — burada kendi IP'sini (TestClient sabit host kullanır)
        # limitin ÜZERİNE çıkaracak kadar çok istek atarak tetikliyoruz.
        son_yanit = None
        for _ in range(50):
            son_yanit = client.post(
                "/auth/login", json={"email": "hic-yok@x.com", "password": "x" * 10}
            )
            if son_yanit.status_code == 429:
                break
        assert son_yanit is not None
        assert son_yanit.status_code == 429
        assert "Retry-After" in son_yanit.headers
    finally:
        client.__exit__(None, None, None)
