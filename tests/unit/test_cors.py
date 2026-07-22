"""#45 — CORS allowlist testleri.

CORS'u yalnız tarayıcı uygular; bu yüzden davranışı değil, backend'in döndürdüğü
başlıkları doğruluyoruz (curl/pytest'te "her şey çalışıyor" tuzağına karşı).
Son iki test, config.py'deki _decode_cors_origins yazılana kadar KIRMIZI kalır.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ensemble.app import create_app
from ensemble.config import Settings

ALLOWED = "http://localhost:5173"


def make_client() -> TestClient:
    # Hermetik: geliştiricinin .env'i teste sızmasın (test_config.py deseni).
    return TestClient(create_app(Settings(_env_file=None)))


def test_izinli_origin_cors_basligi_alir():
    # /health artik RadarServiceDep gerektiriyor (#53) - lifespan'in
    # app.state.radar_service'i kurmasi icin context manager sart.
    with make_client() as client:
        r = client.get("/health", headers={"Origin": ALLOWED})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == ALLOWED


def test_izinsiz_origin_cors_basligi_almaz():
    with make_client() as client:
        r = client.get("/health", headers={"Origin": "https://kotu.example"})
    # İstek 200 döner (CORS'u tarayıcı keser) ama izin başlığı YOK olmalı.
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


def test_preflight_options_izinli_origine_200():
    r = make_client().options(
        "/radar",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == ALLOWED


def test_env_virgullu_string_listeye_cozulur(monkeypatch):
    # KIRMIZI → _decode_cors_origins yazılınca YEŞİL.
    monkeypatch.setenv("CORS_ORIGINS", " https://a.example, https://b.example ,")
    s = Settings(_env_file=None)
    assert s.CORS_ORIGINS == ["https://a.example", "https://b.example"]


def test_wildcard_reddedilir():
    # KIRMIZI → _decode_cors_origins yazılınca YEŞİL. Issue #45: asla "*".
    with pytest.raises(ValidationError, match="içeremez"):
        Settings(_env_file=None, CORS_ORIGINS=["https://a.example", "*"])
