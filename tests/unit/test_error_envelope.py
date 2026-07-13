"""Hata zarfi (#54) testleri — sozlesme: docs/sprint2-kontratlar.md Ek D.

Her hata sinifi icin: dogru status + zarf semasi + CORS basligi; fallback'in
detay sizdirmadigi (hosted) / ozet verdigi (local); Retry-After vatandasligi.
"""

import pytest
from fastapi.testclient import TestClient

from ensemble.api.deps import get_radar_service
from ensemble.api.errors import ErrorEnvelope
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.integrations.gemini.errors import GeminiPermanentError, GeminiTransientError
from ensemble.integrations.github.errors import (
    GitHubAuthError,
    GitHubConfigError,
    GitHubRateLimitError,
    GitHubTransientError,
)

_ORIGIN = "http://localhost:5173"  # varsayilan CORS allowlist'inde


class _Boom:
    def __init__(self, exc: Exception):
        self.exc = exc

    def get_detections(self):
        raise self.exc


def _client(exc: Exception, mode: str = "local") -> TestClient:
    app = create_app(Settings(ENSEMBLE_MODE=mode))
    app.dependency_overrides[get_radar_service] = lambda: _Boom(exc)
    # raise_server_exceptions=False: 500 yolu cevap olarak gelsin, test patlamasin
    return TestClient(app, raise_server_exceptions=False)


# Nobetci string: TR mesajlarla tesadufi kelime cakismasi imkansiz olsun
_SENTINEL = "SENTINEL-IC-DETAY-9x7"


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (GitHubRateLimitError(_SENTINEL), 503, "rate_limited"),
        (GitHubConfigError(_SENTINEL), 503, "github_config"),
        (GitHubAuthError(_SENTINEL), 502, "github_auth"),
        (GitHubTransientError(_SENTINEL), 503, "github_unavailable"),
        (GeminiTransientError(_SENTINEL), 503, "gemini_unavailable"),
        (GeminiPermanentError(_SENTINEL), 502, "gemini_error"),
    ],
)
def test_domain_hatalari_zarfla_doner(exc, status, code):
    resp = _client(exc).get("/radar", headers={"Origin": _ORIGIN})
    assert resp.status_code == status
    body = ErrorEnvelope.model_validate(resp.json())  # sema sozlesmesi
    assert body.error == code
    assert body.status == status
    # ic detay kullanici cevabinin HICBIR yerine sizmaz (mesaj + govde)
    assert _SENTINEL not in resp.text
    # CORS-on-error: tarayici gercek hatayi gorebilmeli (#45/#150 dersi)
    assert resp.headers.get("access-control-allow-origin") == _ORIGIN
    if status == 503:
        assert resp.headers.get("retry-after") == "30"
    else:
        assert "retry-after" not in resp.headers


def test_fallback_local_ozet_verir_stacktrace_vermez():
    resp = _client(RuntimeError("gizli ic detay")).get("/radar", headers={"Origin": _ORIGIN})
    assert resp.status_code == 500
    body = ErrorEnvelope.model_validate(resp.json())
    assert body.error == "internal"
    # local: tur adi + ozet VAR (hizli teshis) — ama stacktrace YOK
    assert "RuntimeError" in body.message
    assert "Traceback" not in resp.text
    # 500 fallback'i CORSMiddleware'in DISINDA kosar — baslik elle eklenmis olmali
    assert resp.headers.get("access-control-allow-origin") == _ORIGIN


def test_fallback_hosted_genericdir_detay_sizdirmaz():
    resp = _client(RuntimeError("gizli ic detay"), mode="hosted").get("/radar")
    assert resp.status_code == 500
    body = ErrorEnvelope.model_validate(resp.json())
    assert body.error == "internal"
    assert "gizli ic detay" not in resp.text
    assert "RuntimeError" not in body.message


def test_izinsiz_origin_cors_basligi_almaz():
    resp = _client(GitHubTransientError("x")).get(
        "/radar", headers={"Origin": "https://kotu.example"}
    )
    assert resp.status_code == 503
    assert "access-control-allow-origin" not in resp.headers


def test_normal_akis_etkilenmez():
    app = create_app(Settings(ENSEMBLE_MODE="local"))
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "mode": "local"}
