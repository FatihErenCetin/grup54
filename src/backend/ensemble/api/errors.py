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
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ensemble.config import Settings
from ensemble.integrations.gemini.errors import (
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
    502: {"model": ErrorEnvelope, "description": "Kalici saglayici hatasi (GitHub/Gemini)"},
    503: {"model": ErrorEnvelope, "description": "Gecici olarak erisilemez (retry edilebilir)"},
}

# (status, kod, TR mesaj) — mesajlar ic detay tasimaz, kullaniciya soylenebilir
_DOMAIN_MAP: list[tuple[type[Exception], int, str, str]] = [
    # Ozel siniflar ONCE (MRO: RateLimit, Transient'ten turer)
    (GitHubRateLimitError, 503, "rate_limited", "GitHub istek limiti doldu — birazdan yeniden denenecek."),
    (GitHubConfigError, 503, "github_config", "GitHub yapılandırması eksik — .env'deki GITHUB_* alanlarını kontrol edin."),
    (GitHubAuthError, 502, "github_auth", "GitHub kimlik doğrulaması reddedildi — App kurulumunu kontrol edin."),
    (GitHubTransientError, 503, "github_unavailable", "GitHub geçici olarak erişilemez."),
    (GitHubError, 502, "github_error", "GitHub entegrasyonunda hata."),
    (GeminiTransientError, 503, "gemini_unavailable", "Gemini geçici olarak erişilemez."),
    (GeminiPermanentError, 502, "gemini_error", "Gemini isteği kalıcı olarak reddedildi — API anahtarını kontrol edin."),
]


def _envelope_response(
    request: Request, status: int, code: str, message: str, settings: Settings
) -> JSONResponse:
    headers: dict[str, str] = {}
    if status == 503:
        headers["Retry-After"] = _RETRY_AFTER_S
    # CORS-on-error: 500 fallback'i CORSMiddleware'in disinda kosar (docstring);
    # allowlist'teki origin'e basligi elle geri veriyoruz. Domain handler'larda
    # zararsiz tekrar (middleware zaten ekliyor — ayni deger).
    origin = request.headers.get("origin")
    if origin and origin in settings.CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
    body = ErrorEnvelope(error=code, message=message, status=status)
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


def register_exception_handlers(app: FastAPI, settings: Settings) -> None:
    for exc_type, status, code, message in _DOMAIN_MAP:

        def handler(
            request: Request,
            exc: Exception,
            status: int = status,
            code: str = code,
            message: str = message,
        ) -> JSONResponse:
            logger.warning("%s: %s (%d %s)", type(exc).__name__, exc, status, code)
            return _envelope_response(request, status, code, message, settings)

        app.add_exception_handler(exc_type, handler)

    def fallback(request: Request, exc: Exception) -> JSONResponse:
        # Tam iz HER modda log'a — zarf asla stacktrace tasimaz
        logger.error("Beklenmedik hata: %s", traceback.format_exc())
        if settings.ENSEMBLE_MODE == "local":
            message = f"Beklenmedik hata: {type(exc).__name__}: {exc}"
        else:
            message = "Beklenmedik bir hata oluştu."
        return _envelope_response(request, 500, "internal", message, settings)

    app.add_exception_handler(Exception, fallback)
