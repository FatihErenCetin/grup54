"""Global hata zarfi (#54) — 500+stacktrace yerine tek tip, temiz JSON.

Sozlesme (Ek D, docs/sprint2-kontratlar.md): HER hata cevabi ayni zarfi tasir:
  {error: <makine-okur kod>, message: <insan-okur TR, ic detay SIZDIRMAZ>, status: <int>}

Uc karar (brifing #54):
- Fallback 500 mesaji MOD-BAGIMLI icerik, SABIT sema: local = tek kullanici
  kendi makinesi (sizinti hedefi yok, hizli teshis kritik) → exception ozeti;
  hosted = paylasilan demo → generic. Tam traceback iki modda da LOG'a.
- Transient/rate-limit 503'lerine Retry-After (dogru HTTP vatandasligi; MCP/
  ucuncu araclar bedava okur — frontend'e okuma zorunlulugu YOK).
- Zarf spec'e ERROR_RESPONSES sabitiyle girer (tek kaynak) → uretilen TS
  client'ta error tarafi tiplenir (#20 zinciri).

CORS notu: Starlette'te Exception (500) fallback'i ServerErrorMiddleware'de
(en dis katman) kosar — CORSMiddleware'in DISINDA. Basligi elle ekliyoruz;
yoksa tarayici gercek 500'u "CORS error" diye gizler (#45/#150 dersi).
Domain-hata handler'lari (ExceptionMiddleware, ic katman) icin CORS otomatik.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ensemble.config import Settings
from starlette.exceptions import HTTPException as StarletteHTTPException

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

logger = logging.getLogger("ensemble.errors")

# Rate-limit'te GitHub reset zamani tasinmiyorsa uydurma sure YOK — konservatif sabit
_RETRY_AFTER_S = "30"


class ErrorEnvelope(BaseModel):
    error: str
    message: str
    status: int


# OpenAPI beyani — router baglanirken tek parametre (app.py); 500 bilerek
# beyan edilmez (evrensel varsayilan), 422 FastAPI otomatigi.
ERROR_RESPONSES = {
    502: {
        "model": ErrorEnvelope,
        "description": "Kalici saglayici hatasi (GitHub/Gemini/Ollama)",
    },
    503: {
        "model": ErrorEnvelope,
        "description": "Gecici olarak erisilemez",
        # Baslik vaadi spec'te gorunur olsun (Ek D) — yalniz transient
        # durumlarda gonderilir (rate limit / 5xx / timeout)
        "headers": {
            "Retry-After": {
                "description": "Saniye — yalniz kendiliginden duzelebilir durumlarda",
                "schema": {"type": "integer"},
            }
        },
    },
}

# (status, kod, TR mesaj, retry_after) — mesajlar ic detay tasimaz.
# Retry-After yalniz KENDILIGINDEN duzelebilecek durumlara (config eksigi 30
# saniyede duzelmez — otomatik istemciyi bosuna retry'a tesvik etme).
# Siralama okunabilirlik icindir: Starlette handler'i type(exc).__mro__
# yuruyerek bulur — kayit sirasi davranisi ETKILEMEZ.
_DOMAIN_MAP: list[tuple[type[Exception], int, str, str, bool]] = [
    (
        GitHubRateLimitError,
        503,
        "rate_limited",
        "GitHub istek limiti doldu — birazdan yeniden denenecek.",
        True,
    ),
    (
        GitHubConfigError,
        503,
        "github_config",
        "GitHub yapılandırması eksik — .env'deki GITHUB_* alanlarını kontrol edin.",
        False,
    ),
    (
        GitHubAuthError,
        502,
        "github_auth",
        "GitHub kimlik doğrulaması reddedildi — App kurulumunu kontrol edin.",
        False,
    ),
    (GitHubTransientError, 503, "github_unavailable", "GitHub geçici olarak erişilemez.", True),
    (GitHubError, 502, "github_error", "GitHub entegrasyonunda hata.", False),
    (GeminiTransientError, 503, "gemini_unavailable", "Gemini geçici olarak erişilemez.", True),
    (
        GeminiPermanentError,
        502,
        "gemini_error",
        "Gemini isteği kalıcı olarak reddedildi — API anahtarını kontrol edin.",
        False,
    ),
    # Taban siniflar da esli: dogrudan taban firlatilirsa 500 fallback'ine
    # dusup (local modda) ic detay sizdirmasin — asimetri bulgusu
    (GeminiError, 502, "gemini_error", "Gemini entegrasyonunda hata.", False),
    (
        OllamaTransientError,
        503,
        "ollama_unavailable",
        "Ollama gecici olarak erisilemez.",
        True,
    ),
    (
        OllamaPermanentError,
        502,
        "ollama_error",
        "Ollama istegi reddedildi - model ve yerel servis ayarlarini kontrol edin.",
        False,
    ),
    (OllamaError, 502, "ollama_error", "Ollama entegrasyonunda hata.", False),
]


def _envelope_response(
    status: int, code: str, message: str, retry_after: bool = False
) -> JSONResponse:
    headers: dict[str, str] = {}
    if retry_after:
        headers["Retry-After"] = _RETRY_AFTER_S
    body = ErrorEnvelope(error=code, message=message, status=status)
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


def _add_cors_headers(response: JSONResponse, request: Request, settings: Settings) -> None:
    """YALNIZ 500 fallback'i icin: ServerErrorMiddleware CORSMiddleware'in
    DISINDA kosar, baslik elle eklenmezse tarayici gercek hatayi 'CORS error'
    diye gizler. Domain handler'lari IC katmanda — middleware otomatik ekler;
    orada elle eklemek Vary: 'Origin, Origin' duplikasyonu uretiyordu
    (adversarial dogrulama deneyi)."""
    origin = request.headers.get("origin")
    if origin and origin in settings.CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"


def register_exception_handlers(app: FastAPI, settings: Settings) -> None:
    for exc_type, status, code, message, retry_after in _DOMAIN_MAP:

        def handler(
            request: Request,
            exc: Exception,
            status: int = status,
            code: str = code,
            message: str = message,
            retry_after: bool = retry_after,
        ) -> JSONResponse:
            logger.warning("%s: %s (%d %s)", type(exc).__name__, exc, status, code)
            return _envelope_response(status, code, message, retry_after)

        app.add_exception_handler(exc_type, handler)

    def http_exception(request: Request, exc: Exception) -> JSONResponse:
        # 404/405 gibi framework HTTP hatalari da ayni zarfi tasir ("tek tip"
        # vaadi eksiksiz olsun); 422 istisnasi Ek D'de beyanli (FastAPI semasi)
        status = getattr(exc, "status_code", 500)
        detail = str(getattr(exc, "detail", "")) or "HTTP hatası"
        return _envelope_response(status, f"http_{status}", detail)

    app.add_exception_handler(StarletteHTTPException, http_exception)

    def fallback(request: Request, exc: Exception) -> JSONResponse:
        # Tam iz HER modda log'a — zarf asla stacktrace tasimaz.
        # exc_info=exc SART: sync handler Starlette'te AYRI thread'de kosar,
        # sys.exc_info() orada bos → format_exc() "NoneType: None" uretiyordu
        # (adversarial dogrulama bulgusu). Not: uvicorn ayrica kendi
        # "Exception in ASGI application" kaydini basar (re-raise) — cift
        # ERROR bilincli/bilinen davranis.
        logger.error("Beklenmedik hata", exc_info=exc)
        if settings.ENSEMBLE_MODE == "local":
            message = f"Beklenmedik hata: {type(exc).__name__}: {exc}"
        else:
            message = "Beklenmedik bir hata oluştu."
        response = _envelope_response(500, "internal", message)
        _add_cors_headers(response, request, settings)
        return response

    app.add_exception_handler(Exception, fallback)
