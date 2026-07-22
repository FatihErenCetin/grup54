"""Hata zarfi (#54) testleri — sozlesme: docs/sprint2-kontratlar.md Ek D.

Her hata sinifi icin: dogru status + zarf semasi + CORS basligi; fallback'in
detay sizdirmadigi (hosted) / ozet verdigi (local); Retry-After vatandasligi.
"""

import pytest
from fastapi.testclient import TestClient

from ensemble.api.deps import get_query_service, get_radar_service, get_scope_service
from ensemble.api.errors import ErrorEnvelope
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.engine.query import QueryInputError, QueryJudgeError, QueryRetrievalError
from ensemble.engine.scope import ScopeJudgeError, ScopeReferenceError, ScopeUnavailableError
from ensemble.integrations.gemini.errors import (
    GeminiError,
    GeminiPermanentError,
    GeminiTransientError,
)
from ensemble.integrations.github.errors import (
    GitHubAuthError,
    GitHubConfigError,
    GitHubError,
    GitHubRateLimitError,
    GitHubTransientError,
)
from ensemble.integrations.ollama.errors import (
    OllamaError,
    OllamaPermanentError,
    OllamaTransientError,
)

_ORIGIN = "http://localhost:5173"  # varsayilan CORS allowlist'inde


class _Boom:
    def __init__(self, exc: Exception):
        self.exc = exc

    def get_detections(self):
        raise self.exc


class _BoomQuery:
    def __init__(self, exc: Exception):
        self.exc = exc

    def ask(self, question: str):
        raise self.exc


class _BoomScope:
    def __init__(self, exc: Exception):
        self.exc = exc

    def check_scope(self, ref: str):
        raise self.exc


def _client(exc: Exception, mode: str = "local") -> TestClient:
    app = create_app(Settings(ENSEMBLE_MODE=mode))
    app.dependency_overrides[get_radar_service] = lambda: _Boom(exc)
    # raise_server_exceptions=False: 500 yolu cevap olarak gelsin, test patlamasin
    return TestClient(app, raise_server_exceptions=False)


# Nobetci string: TR mesajlarla tesadufi kelime cakismasi imkansiz olsun
_SENTINEL = "SENTINEL-IC-DETAY-9x7"


@pytest.mark.parametrize(
    ("exc", "status", "code", "retry_after"),
    [
        (GitHubRateLimitError(_SENTINEL), 503, "rate_limited", True),
        # config eksigi 30 sn'de duzelmez → Retry-After bilerek YOK (Ek D)
        (GitHubConfigError(_SENTINEL), 503, "github_config", False),
        (GitHubAuthError(_SENTINEL), 502, "github_auth", False),
        (GitHubTransientError(_SENTINEL), 503, "github_unavailable", True),
        (GitHubError(_SENTINEL), 502, "github_error", False),  # taban — gercek yol: client.py
        (GeminiTransientError(_SENTINEL), 503, "gemini_unavailable", True),
        (GeminiPermanentError(_SENTINEL), 502, "gemini_error", False),
        (GeminiError(_SENTINEL), 502, "gemini_error", False),  # taban asimetrisi kapali
        (OllamaTransientError(_SENTINEL), 503, "ollama_unavailable", True),
        (OllamaPermanentError(_SENTINEL), 502, "ollama_error", False),
        (OllamaError(_SENTINEL), 502, "ollama_error", False),
    ],
)
def test_domain_hatalari_zarfla_doner(exc, status, code, retry_after):
    resp = _client(exc).get("/radar", headers={"Origin": _ORIGIN})
    assert resp.status_code == status
    body = ErrorEnvelope.model_validate(resp.json())  # sema sozlesmesi
    assert body.error == code
    assert body.status == status
    # ic detay kullanici cevabinin HICBIR yerine sizmaz (mesaj + govde)
    assert _SENTINEL not in resp.text
    # CORS-on-error: tarayici gercek hatayi gorebilmeli (#45/#150 dersi)
    assert resp.headers.get("access-control-allow-origin") == _ORIGIN
    # Vary duplikasyonu yok (elle-CORS yalniz 500 fallback'inde)
    assert resp.headers.get("vary") == "Origin"
    if retry_after:
        assert resp.headers.get("retry-after") == "30"
    else:
        assert "retry-after" not in resp.headers


def test_fallback_local_ozet_verir_stacktrace_vermez():
    resp = _client(RuntimeError("gizli ic detay")).get("/radar", headers={"Origin": _ORIGIN})
    assert resp.status_code == 500
    body = ErrorEnvelope.model_validate(resp.json())
    assert body.error == "internal"
    # local: tur adi + MESAJ ozeti VAR (hizli teshis, bilincli) — stacktrace YOK
    assert "RuntimeError" in body.message
    assert "gizli ic detay" in body.message
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


def test_fallback_traceback_loga_yazilir(caplog):
    # exc_info=exc SART: sync handler ayri thread'de kosar, format_exc bos
    # donuyordu ("NoneType: None") — adversarial dogrulama blocker'i
    import logging

    with caplog.at_level(logging.ERROR, logger="ensemble.errors"):
        resp = _client(RuntimeError("iz-sondasi-123")).get("/radar")
    assert resp.status_code == 500
    assert "Traceback" in caplog.text
    assert "iz-sondasi-123" in caplog.text
    assert "Traceback" not in resp.text  # zarf asla iz tasimaz


def test_framework_http_hatalari_da_zarfta():
    app = create_app(Settings(ENSEMBLE_MODE="local"))
    resp = TestClient(app).get("/boyle-bir-yol-yok")
    assert resp.status_code == 404
    body = ErrorEnvelope.model_validate(resp.json())
    assert body.error == "http_404"


def test_preflight_calisiyor():
    # CORS'un preflight bacagi da korunuyor (allow_methods=[GET])
    app = create_app(Settings(ENSEMBLE_MODE="local"))
    resp = TestClient(app).options(
        "/radar",
        headers={"Origin": _ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == _ORIGIN
    assert "GET" in resp.headers.get("access-control-allow-methods", "")


@pytest.mark.parametrize(
    ("exc", "status", "code", "retry_after"),
    [
        (QueryInputError(_SENTINEL), 400, "query_invalid", False),
        (
            QueryRetrievalError(_SENTINEL),
            503,
            "query_retrieval_unavailable",
            True,
        ),
        (QueryJudgeError(_SENTINEL), 502, "query_judge_error", False),
    ],
)
def test_query_hatalari_acik_ama_ic_detaysiz_zarfla_doner(
    exc,
    status,
    code,
    retry_after,
):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_query_service] = lambda: _BoomQuery(exc)

    response = TestClient(app).get("/query", params={"q": "scope nedir"})

    assert response.status_code == status
    assert response.json()["error"] == code
    assert _SENTINEL not in response.text
    assert ("retry-after" in response.headers) is retry_after


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (ScopeReferenceError(_SENTINEL), 404, "scope_ref_not_found"),
        (ScopeUnavailableError(_SENTINEL), 503, "scope_unavailable"),
        (ScopeJudgeError(_SENTINEL), 502, "scope_judge_error"),
    ],
)
def test_scope_hatalari_acik_ama_ic_detaysiz_zarfla_doner(exc, status, code):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_scope_service] = lambda: _BoomScope(exc)

    response = TestClient(app).get("/scope/check", params={"ref": "PR-42"})

    assert response.status_code == status
    assert response.json()["error"] == code
    assert _SENTINEL not in response.text
