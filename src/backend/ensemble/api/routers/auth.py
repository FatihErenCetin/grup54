"""Kullanıcı girişi (#79 daraltılmış dilim) — GitHub App kullanıcı-yetkilendirme
akışı + imzalı çerez oturumu.

Sözleşme (kanonik, brifing):
  GET  /auth/config    -> 200 {"enabled": bool}           HER ZAMAN 200
  GET  /auth/login     -> 302 GitHub yetkilendirme adresine (enabled=false -> 503)
  GET  /auth/callback  -> 302 frontend'e + Set-Cookie (oturum)
  GET  /auth/me        -> 200 {"handle": str, "avatar_url": str|None} | 401
  POST /auth/logout    -> 204, çerezi siler

KRİTİK: bu router yalnızca "kim olduğunu göster" katmanıdır — hiçbir mevcut
uç (radar/board/scope/query/...) buna bağımlı DEĞİL; giriş yapılandırılmamışsa
uygulama hiçbir şekilde kapanmaz, yalnız bu 5 uçtan ikisi (login/callback)
503 döner (#79 kuralı, config.py::Settings.auth_enabled).

access_token BURADA HİÇBİR YERDE SAKLANMAZ (#79'un kendi kuralı) — yalnız
`callback` içinde `/user` çağrısı için kullanılır, sonra atılır. Kullanıcı/
identity DB tablosu, installation picker, çok-kiracılık = #79'un AYRI/kalan
dilimi (bu dosyanın kapsamı DIŞINDA).
"""

import hmac
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel

from ensemble.api.auth_session import (
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
    SessionSignatureError,
    sign_session,
    verify_session,
)
from ensemble.api.deps import SettingsDep
from ensemble.config import Settings
from ensemble.integrations.github.oauth import (
    build_authorize_url,
    exchange_code_for_token,
    fetch_github_user,
)

logger = logging.getLogger("ensemble.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# State çerezi yalnız OAuth gidiş-dönüşü boyunca yaşar (birkaç dakikalık
# tarayıcı yolculuğu); session çerezi çok daha uzun ömürlü — "giriş yaptım"
# bilgisi günler boyunca kalıcı olmalı.
_STATE_COOKIE_MAX_AGE_S = 600
_SESSION_COOKIE_MAX_AGE_S = 60 * 60 * 24 * 30


def _cookie_kwargs(settings: Settings) -> dict:
    """set_cookie/delete_cookie'de TEK kaynaktan paylaşılan öznitelikler —
    üçü de (login/callback/logout) aynı Domain/Secure/HttpOnly/SameSite'ı
    kullanmazsa tarayıcı bunları FARKLI çerezler sanır (silme no-op kalır)."""
    return {
        "domain": settings.AUTH_COOKIE_DOMAIN,
        "httponly": True,
        "secure": True,
        "samesite": "lax",
    }


class AuthConfigResponse(BaseModel):
    enabled: bool


class AuthUserResponse(BaseModel):
    handle: str
    avatar_url: str | None


@router.get("/config")
def auth_config(settings: SettingsDep) -> AuthConfigResponse:
    # Sırlar yoksa da HER ZAMAN 200 — uygulama giriş yapılandırılmadan da
    # açılır (#79 kuralı); bu uç yalnız "giriş mümkün mü" sinyalini taşır.
    return AuthConfigResponse(enabled=settings.auth_enabled)


@router.get("/login")
def github_login(request: Request, settings: SettingsDep) -> RedirectResponse:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "Giriş yapılandırılmamış — GITHUB_OAUTH_CLIENT_ID/"
                "GITHUB_OAUTH_CLIENT_SECRET/AUTH_SESSION_SECRET eksik"
            ),
        )

    redirect_uri = str(request.url_for("github_oauth_callback"))
    state = secrets.token_urlsafe(32)
    authorize_url = build_authorize_url(settings, redirect_uri=redirect_uri, state=state)

    response = RedirectResponse(authorize_url, status_code=302)
    response.set_cookie(
        STATE_COOKIE_NAME, state, max_age=_STATE_COOKIE_MAX_AGE_S, **_cookie_kwargs(settings)
    )
    return response


@router.get("/callback")
def github_oauth_callback(
    request: Request,
    settings: SettingsDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    # GitHub'ın kendi hatası (kullanıcı "İptal"e bastı vb.) — DÜRÜSTÇE ele
    # alınır: 500'e düşmez, oturum açılmadan sessizce frontend'e döner.
    if error:
        logger.warning("GitHub OAuth reddedildi: %s (%s)", error, error_description)
        response = RedirectResponse(settings.AUTH_POST_LOGIN_URL, status_code=302)
        response.delete_cookie(STATE_COOKIE_NAME, **_cookie_kwargs(settings))
        return response

    if not settings.auth_enabled:
        raise HTTPException(status_code=503, detail="Giriş yapılandırılmamış")

    cookie_state = request.cookies.get(STATE_COOKIE_NAME)
    state_ok = bool(code and state and cookie_state and hmac.compare_digest(cookie_state, state))
    if not state_ok:
        raise HTTPException(
            status_code=400,
            detail="state doğrulanamadı — OAuth akışı yeniden başlatılmalı (/auth/login)",
        )

    redirect_uri = str(request.url_for("github_oauth_callback"))
    # exchange_code_for_token/fetch_github_user GitHubAuthError/GitHubTransientError
    # fırlatabilir — bunlar burada YUTULMAZ, api/errors.py::_DOMAIN_MAP zaten
    # ikisini de (502/503) standart zarfa çeviriyor (yeniden icat edilmez).
    access_token = exchange_code_for_token(settings, code=code, redirect_uri=redirect_uri)
    handle, avatar_url = fetch_github_user(access_token)
    # access_token burada biter — DB'ye/cache'e YAZILMAZ (#79 kuralı).

    session_token = sign_session(settings.AUTH_SESSION_SECRET, handle=handle, avatar_url=avatar_url)
    response = RedirectResponse(settings.AUTH_POST_LOGIN_URL, status_code=302)
    response.delete_cookie(STATE_COOKIE_NAME, **_cookie_kwargs(settings))
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=_SESSION_COOKIE_MAX_AGE_S,
        **_cookie_kwargs(settings),
    )
    return response


@router.get("/me", responses={401: {"description": "Oturum yok/geçersiz"}})
def auth_me(request: Request, settings: SettingsDep) -> AuthUserResponse:
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie or not settings.AUTH_SESSION_SECRET:
        raise HTTPException(status_code=401, detail="Oturum bulunamadı")
    try:
        payload = verify_session(settings.AUTH_SESSION_SECRET, cookie)
    except SessionSignatureError as exc:
        raise HTTPException(status_code=401, detail="Oturum geçersiz") from exc
    return AuthUserResponse(handle=payload["handle"], avatar_url=payload.get("avatar_url"))


@router.post("/logout", status_code=204)
def auth_logout(settings: SettingsDep) -> Response:
    # Oturum olsun olmasın idempotent 204 — çıkış yapmak için giriş şart değil.
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE_NAME, **_cookie_kwargs(settings))
    return response
