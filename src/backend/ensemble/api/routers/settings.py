"""Yerel sağlayıcı ayarları (T-307 FAZ 2) — kullanıcı kendi API anahtarını
ayarlar sayfasından girer, `.env`'e hiç dokunmadan.

Sözleşme (sabit, frontend ajanı bunu üretilen client'a göre tüketiyor):
  GET  /settings/saglayici -> {mode, saglayici, anahtarlar: {gemini, groq}, ollama_url}
  PUT  /settings/saglayici    {saglayici, anahtar?, ollama_url?} -> 200 (aynı zarf)
  POST /settings/test         {saglayici} -> {calisiyor, mesaj}
  GET  /settings/mcp       -> {config_json, yol}

BEŞ GÜVENLİK KURALI (görev brifingi, T-307):
  1. `ENSEMBLE_MODE != "local"` -> bu uçların HEPSİ 404 (`_require_local_mode`).
     Hosted'da bu uçlar var olsaydı, siteye giren HERKES sunucunun gerçek
     API anahtarlarını değiştirebilir/okuyabilirdi.
  2. `GET` anahtarı ASLA tam döndürmez — yalnız maskelenmiş (`_mask_key`).
  3. Anahtarlar repoda/git'te/DB'de DEĞİL — `store/provider_settings.py`
     (`~/.ensemble/ayarlar.json`, izin 0600).
  4. `POST /settings/test` GERÇEK bir ağ çağrısı yapar (liste/metadata uçları
     — üretim kotasını YAKMAZ) ve başarısızlığı kategori bilgisiyle (yetki/
     kota/ağ) döner — "anahtar dolu = çalışıyor" fail-open'ı YASAK.
  5. Kaydetme GERÇEKTEN devreye girer: `app.state.settings` yeniden kurulur
     VE etkilenen judge/embeddings/github port'ları `ensemble.app.
     rebuild_llm_services` ile YENİDEN İNŞA edilir (bkz. o fonksiyonun
     docstring'i — `GeminiJudgeAdapter` gibi adaptörler kurucuda YAKALADIĞI
     `Settings`'i sonradan yeniden okumaz, port'un KENDİSİ değişmeli).

Döngüsel import notu: `ensemble.app` bu router'ı `create_app()` içinde
BAĞLAR (`app.include_router(settings.router, ...)`), bu yüzden bu modül
`ensemble.app`'i MODÜL SEVİYESİNDE import EDEMEZ (döngü). `rebuild_llm_services`/
`apply_provider_overlay` bu yüzden İSTEK-ANINDA (fonksiyon içinde, gecikmeli)
import edilir — o ana kadar `ensemble.app` zaten tam yüklenmiş olur.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from google import genai
from google.genai import errors as genai_errors
from google.genai.types import HttpOptions
from pydantic import BaseModel

from ensemble.api.deps import SettingsDep
from ensemble.config import Settings, normalize_local_ollama_url
from ensemble.store.provider_settings import read_provider_settings, write_provider_settings

logger = logging.getLogger("ensemble.settings")

router = APIRouter(prefix="/settings", tags=["settings"])

# repo kökü — `config.py::_REPO_ROOT` ile AYNI hesap (dosya ensemble/api/
# routers/'ta, config.py ise ensemble/'de yaşıyor; bu yüzden özel bir sabiti
# modül sınırları arasında İTHAL ETMEK yerine — repo genelinde testlerin de
# yaptığı gibi — burada kendi hesabımızı tutuyoruz).
_REPO_ROOT = Path(__file__).resolve().parents[5]

# 404 (KURAL 1: yalnız local mod) DÖRT UCUN DA ORTAK davranışı — router-özel
# `responses=` yerine `ensemble.app::create_app`'in `app.include_router(
# settings.router, responses=...)` çağrısında merge edilir (health/scope/
# auth router'larıyla AYNI ilke: paylaşılan zarf TEK noktada). 422 burada
# AYRICA beyan EDİLMEZ — Pydantic gövdeli her route'ta FastAPI'nin kendi
# otomatiği (bkz. `api/errors.py` docstring'i, "422 FastAPI otomatigi").


def _require_local_mode(settings: Settings) -> None:
    """KURAL 1 — hosted'da bu uçlar YOK SAYILIR (404, "yasak" 403 DEĞİL —
    varlığını bile ifşa etmemek için standart "kaynak yok" davranışı)."""
    if settings.ENSEMBLE_MODE != "local":
        raise HTTPException(status_code=404, detail="Bu uç yalnız local modda vardır.")


def _mask_key(value: str | None) -> str | None:
    """KURAL 2 — tam anahtar ASLA dönmez. `ANAH...4f2c` gibi bir değer için
    `ANAH…4f2c` (ilk 4 + `…` + son 4) döner. Kısa değerlerde (ör. testte
    kullanılan `k` gibi fixture anahtarları) ilk+son 4 karakter kuralı
    anahtarın TAMAMINI (ya da fazlasını) ifşa ederdi — bu yüzden kısa
    değerler için daha az karakter gösterilir, hiçbiri için TAMAMI değil."""
    if not value:
        return None
    if len(value) > 8:
        return f"{value[:4]}…{value[-4:]}"
    if len(value) > 4:
        return f"{value[:2]}…{value[-2:]}"
    return "…"


class ProviderKeys(BaseModel):
    gemini: str | None = None
    groq: str | None = None


class ProviderSettingsResponse(BaseModel):
    mode: Literal["local", "hosted"]
    saglayici: Literal["gemini", "ollama"]
    anahtarlar: ProviderKeys
    ollama_url: str


class ProviderUpdateRequest(BaseModel):
    saglayici: Literal["gemini", "groq", "ollama"]
    anahtar: str | None = None
    ollama_url: str | None = None


class ProviderTestRequest(BaseModel):
    saglayici: Literal["gemini", "groq", "ollama"]


class ProviderTestResponse(BaseModel):
    calisiyor: bool
    mesaj: str


class McpConfigResponse(BaseModel):
    config_json: str
    yol: str


def _current_response(settings: Settings) -> ProviderSettingsResponse:
    return ProviderSettingsResponse(
        mode=settings.ENSEMBLE_MODE,
        saglayici=settings.LLM_PROVIDER,
        anahtarlar=ProviderKeys(
            gemini=_mask_key(settings.GEMINI_API_KEY),
            groq=_mask_key(settings.GROQ_API_KEY or None),
        ),
        ollama_url=settings.OLLAMA_BASE_URL,
    )


@router.get("/saglayici")
def get_provider_settings(settings: SettingsDep) -> ProviderSettingsResponse:
    _require_local_mode(settings)
    return _current_response(settings)


@router.put("/saglayici")
def update_provider_settings(
    payload: ProviderUpdateRequest, request: Request, settings: SettingsDep
) -> ProviderSettingsResponse:
    _require_local_mode(settings)

    normalized_ollama_url: str | None = None
    if payload.saglayici == "ollama" and payload.ollama_url:
        try:
            normalized_ollama_url = normalize_local_ollama_url(payload.ollama_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    data = read_provider_settings()
    if payload.saglayici in ("gemini", "ollama"):
        # `saglayici` gemini/ollama ise AYNI ZAMANDA aktif LLM_PROVIDER'ı
        # değiştirir (radio-button semantiği) — groq yalnız bir YEDEK anahtar
        # slotu, hiçbir zaman LLM_PROVIDER olamaz (bkz. app.py::_build_judge_port
        # — Groq yalnız Gemini birincilken devreye giren bir FallbackJudge).
        data["llm_provider"] = payload.saglayici
    if payload.saglayici == "gemini" and payload.anahtar:
        data["gemini_api_key"] = payload.anahtar
    if payload.saglayici == "groq" and payload.anahtar:
        data["groq_api_key"] = payload.anahtar
    if payload.saglayici == "ollama" and normalized_ollama_url:
        data["ollama_base_url"] = normalized_ollama_url
    write_provider_settings(data)

    # KURAL 5 — kaydetmek yetmez, ÇALIŞAN SÜRECE devretmek gerekir.
    # Gecikmeli import: bkz. modül docstring'i (döngüsel import notu).
    from ensemble.app import apply_provider_overlay, rebuild_llm_services
    from ensemble.config import get_settings as _module_get_settings

    _module_get_settings.cache_clear()  # savunmacı — bkz. docstring
    request.app.state.settings = apply_provider_overlay(request.app.state.base_settings)
    rebuild_llm_services(request.app)

    return _current_response(request.app.state.settings)


def _test_gemini(settings: Settings) -> ProviderTestResponse:
    if not settings.GEMINI_API_KEY:
        return ProviderTestResponse(calisiyor=False, mesaj="Gemini anahtarı tanımlı değil.")
    try:
        client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=HttpOptions(timeout=int(settings.GEMINI_TIMEOUT_S * 1000)),
        )
        # `models.get` bir METADATA çağrısıdır (generateContent kotasına
        # DOKUNMAZ) — GEMINI_API_KEY günlük yalnızca 20 istek/gün kotasına
        # sahip (bkz. .env.example yorumu); "test et" butonuna her tıklama
        # bunu tüketseydi kullanıcı gerçek kullanımdan ÖNCE kotayı bitirirdi.
        client.models.get(model=settings.GEMINI_MODEL)
    except genai_errors.APIError as exc:
        code = getattr(exc, "code", None)
        if code in (401, 403):
            return ProviderTestResponse(
                calisiyor=False, mesaj=f"Gemini anahtarı geçersiz veya yetkisiz ({code})."
            )
        if code == 429:
            return ProviderTestResponse(
                calisiyor=False,
                mesaj="Gemini kotası aşıldı (429) — bir süre sonra tekrar deneyin.",
            )
        return ProviderTestResponse(calisiyor=False, mesaj=f"Gemini hata döndü ({code}): {exc}")
    except Exception as exc:  # ağ kopması/timeout vb. SDK-dışı hatalar
        return ProviderTestResponse(
            calisiyor=False, mesaj=f"Gemini'ye ulaşılamadı (ağ hatası): {exc}"
        )
    return ProviderTestResponse(calisiyor=True, mesaj="Bağlantı başarılı.")


def _test_groq(settings: Settings) -> ProviderTestResponse:
    if not settings.GROQ_API_KEY:
        return ProviderTestResponse(calisiyor=False, mesaj="Groq anahtarı tanımlı değil.")
    try:
        with httpx.Client(
            base_url=settings.GROQ_BASE_URL,
            timeout=settings.GROQ_TIMEOUT_S,
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        ) as client:
            # /openai/v1/models — yalnız METADATA listesi, chat-completion
            # (ücretli/kotalı) çağrısı DEĞİL.
            resp = client.get("/openai/v1/models")
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        return ProviderTestResponse(calisiyor=False, mesaj=f"Groq'a ulaşılamadı (ağ hatası): {exc}")
    if resp.status_code in (401, 403):
        return ProviderTestResponse(
            calisiyor=False, mesaj=f"Groq anahtarı geçersiz veya yetkisiz ({resp.status_code})."
        )
    if resp.status_code == 429:
        return ProviderTestResponse(
            calisiyor=False, mesaj="Groq kotası aşıldı (429) — bir süre sonra tekrar deneyin."
        )
    if resp.is_error:
        return ProviderTestResponse(
            calisiyor=False, mesaj=f"Groq hata döndü ({resp.status_code})."
        )
    return ProviderTestResponse(calisiyor=True, mesaj="Bağlantı başarılı.")


def _test_ollama(settings: Settings) -> ProviderTestResponse:
    try:
        with httpx.Client(base_url=settings.OLLAMA_BASE_URL, timeout=settings.OLLAMA_TIMEOUT_S) as client:
            # /api/tags — yerel modelleri listeler, üretim/embedding çağrısı DEĞİL.
            resp = client.get("/api/tags")
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        return ProviderTestResponse(
            calisiyor=False,
            mesaj=f"Ollama'ya ulaşılamadı (ağ hatası) — sunucu çalışıyor mu? {exc}",
        )
    if resp.is_error:
        return ProviderTestResponse(calisiyor=False, mesaj=f"Ollama hata döndü ({resp.status_code}).")
    return ProviderTestResponse(calisiyor=True, mesaj="Bağlantı başarılı.")


@router.post("/test")
def test_provider(payload: ProviderTestRequest, settings: SettingsDep) -> ProviderTestResponse:
    _require_local_mode(settings)
    if payload.saglayici == "gemini":
        return _test_gemini(settings)
    if payload.saglayici == "groq":
        return _test_groq(settings)
    return _test_ollama(settings)


@router.get("/mcp")
def get_mcp_config(settings: SettingsDep) -> McpConfigResponse:
    """T-307 FAZ 4 — hazır `.mcp.json` parçacığı, MUTLAK yol ile (kullanıcının
    kendi makinesindeki gerçek repo kökü). Sahte "bağlandı" durumu ÜRETMEZ —
    yalnız yapıştırılacak içeriği + hedef dosya yolunu döner; Claude Code'un
    (ya da başka bir MCP istemcisinin) bunu OKUMASI için yeniden başlatılması
    GEREKİR (bu uç bunu doğrulayamaz/garanti edemez, dürüstçe belirtir)."""
    _require_local_mode(settings)
    config = {
        "mcpServers": {
            "ensemble": {
                "command": "uv",
                "args": [
                    "run",
                    "--directory",
                    str(_REPO_ROOT),
                    "python",
                    "-m",
                    "ensemble_mcp.server",
                ],
            }
        }
    }
    return McpConfigResponse(
        config_json=json.dumps(config, indent=2, ensure_ascii=False),
        yol=str(_REPO_ROOT / ".mcp.json"),
    )
