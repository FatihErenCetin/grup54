"""Kullanıcı girişi (#79) — GitHub App kullanıcı-yetkilendirme akışı + imzalı
çerez oturumu + çok-kiracılı repo seçimi (T-79, #79'un kalan dilimi). T-294/
D-57 ile email+parola üyeliği bunun YANINA eklendi (bkz.
`.harness/decisions/D-57-email-parola-uyeligi.md`).

Sözleşme (kanonik, brifing + T-294 + T-79):
  GET  /auth/config         -> 200 {"enabled", "email_enabled"}  HER ZAMAN 200
  GET  /auth/login          -> 302 GitHub yetkilendirme adresine (enabled=false -> 503)
  GET  /auth/callback       -> 302 frontend'e + Set-Cookie (oturum)
  POST /auth/register       -> 201 + Set-Cookie (oturum) | 422 politika | 409 e-posta dolu
  POST /auth/login          -> 200 + Set-Cookie (oturum) | 401
  GET  /auth/me             -> 200 {"handle", "avatar_url", "email"} | 401
  POST /auth/logout         -> 204, çerezi siler
  GET  /auth/install-url    -> 200 {"url"}  GitHub App kurulum sayfası (503 yapılandırılmamışsa)
  GET  /auth/install-callback -> 302 (GitHub'ın App kurulumu sonrası yönlendirdiği uç — oturum ZORUNLU)
  GET  /auth/installations  -> 200 {"installations": [...]}  401 oturum yok
  GET  /auth/repos          -> 200 {"selected", "active", "demo"}  401 oturum yok
  PUT  /auth/repos          -> 200 {"selected", "active"}  403 izinsiz repo, 401 oturum yok

KRİTİK: bu router yalnızca "kim olduğunu göster" + "hangi repoyu izliyorum"
katmanıdır — hiçbir mevcut uç (radar/board/scope/query/...) buna KOŞULSUZ
bağımlı DEĞİL (oturum yoksa demo repo görünür, D-23 korunur); giriş
yapılandırılmamışsa uygulama hiçbir şekilde kapanmaz. GitHub OAuth 503'ü
`Settings.auth_enabled`e (3 alan), email register/login 503'ü
`Settings.email_auth_enabled`e (yalnız `AUTH_SESSION_SECRET`) bağlıdır; App
uçları (`install-url`/`installations`) `Settings.app_auth_enabled`e
(`GITHUB_APP_ID` + private key) bağlıdır — ÜÇÜ AYRI KAPI, birbirinden BAĞIMSIZ.

access_token GitHub OAuth akışında HİÇBİR YERDE SAKLANMAZ — yalnız `callback`
içinde `/user` çağrısı için kullanılır, sonra atılır. Installation access
token'ları da AYNI ilkeyle anlık üretilir (integrations/github/app_api.py) —
yalnızca `installation_id` (kalıcı ama SIR OLMAYAN bir kimlik) DB'de kalır.
Email akışının PAROLASI benzer şekilde asla düz metin saklanmaz — yalnız
argon2id hash'i `users.password_hash` kolonuna yazılır.

T-79 GÜNCELLEMESİ: GitHub OAuth callback'i artık (D-57'nin ötesinde,
`identities` tablosu üzerinden) get-or-create bir `UserRow` AÇAR — Installation
picker bir `user_id`'ye ihtiyaç duyduğu için (bkz. store/identity_store.py).
Bu, D-57'nin "hesap birleştirme kapsam dışı" kararını GENİŞLETMEZ: email
hesabıyla otomatik birleştirme YAPILMAZ, yalnızca AYNI GitHub kimliği ikinci
girişte AYNI satıra döner.

Email doğrulama/parola sıfırlama BİLEREK YOK (SMTP yapılandırılmamış; bkz.
D-57 "bilerek yapılmayan").
"""

import hmac
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ensemble.api.auth_session import (
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
    SessionSignatureError,
    sign_session,
    verify_session,
)
from ensemble.api.credentials import (
    EmailFormatError,
    MAX_PASSWORD_LENGTH,
    PasswordPolicyError,
    normalize_email,
    hash_password,
    validate_email_format,
    validate_password_policy,
    verify_password_or_dummy,
)
from ensemble.api.deps import SessionFactoryDep, SettingsDep
from ensemble.api.rate_limit import WindowCounter, client_ip
from ensemble.config import Settings
from ensemble.integrations.github.app_api import (
    fetch_app_slug,
    fetch_installation_repositories,
)
from ensemble.integrations.github.oauth import (
    build_authorize_url,
    exchange_code_for_token,
    fetch_github_user,
)
from ensemble.store.identity_store import get_or_create_github_user
from ensemble.store.installation_store import (
    get_installation_for_user,
    list_installations_for_user,
    list_watched_repos,
    replace_watched_repos,
    upsert_installation,
)
from ensemble.store.user_store import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    set_active_repo,
    touch_last_login,
)

logger = logging.getLogger("ensemble.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# State çerezi yalnız OAuth gidiş-dönüşü boyunca yaşar (birkaç dakikalık
# tarayıcı yolculuğu); session çerezi çok daha uzun ömürlü — "giriş yaptım"
# bilgisi günler boyunca kalıcı olmalı.
_STATE_COOKIE_MAX_AGE_S = 600
_SESSION_COOKIE_MAX_AGE_S = 60 * 60 * 24 * 30

# --- Kaba kuvvet koruması (#294 brifingi madde 7) ---
# DEMO_MODE'daki DemoRateLimitMiddleware'den BAĞIMSIZ + KOŞULSUZ devrede
# (yalnız hosted demo değil, HER kurulumda — parola tahmini/hesap-spam
# saldırı yüzeyi DEMO_MODE'a bağlı değildir). Mevcut `WindowCounter` primitifi
# (rate_limit.py) yeniden kullanılır — yeni bir mekanizma İCAT EDİLMEZ.
# `_STATE_COOKIE_MAX_AGE_S` gibi bu da BİLEREK modül-sabiti (yeni bir .env
# anahtarı DEĞİL) — bu ikisinin dışında hiçbir kurulum tarafından ayarlanması
# gerekmiyor; `.env.example`/`docs/deploy-runbook.md`'ye dokunmadan (drift
# testine dokunmadan) sabit, savunulabilir bir varsayılan yeterli.
# register + login AYNI sayaçta (paylaşılan) — bir saldırgan iki uç arasında
# geçiş yaparak limiti atlatamaz.
_AUTH_RATE_LIMIT = 5
_AUTH_RATE_WINDOW_S = 60
_auth_rate_counter = WindowCounter(_AUTH_RATE_WINDOW_S)

_GENERIC_LOGIN_ERROR = "E-posta ya da parola hatalı."


def _enforce_auth_rate_limit(request: Request) -> None:
    """IP başına `/auth/register` + `/auth/login` deneme limiti — aşılınca
    429 + Retry-After (errors.py::http_exception artık `HTTPException.headers`ı
    yayıyor, bkz. o dosyadaki T-294 notu)."""
    ip = client_ip(request)
    allowed, retry_after = _auth_rate_counter.allow(ip, _AUTH_RATE_LIMIT)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Çok fazla deneme yapıldı — birazdan tekrar deneyin.",
            headers={"Retry-After": str(max(1, int(retry_after)))},
        )


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


def _require_session_user_id(request: Request, settings: Settings) -> str:
    """T-79: Installation picker uçlarının (`/auth/install-callback`,
    `/auth/installations`, `/auth/repos`) HEPSİNİN kullandığı TEK oturum
    kapısı — `sub` (users.id) yoksa 401. `handle`-yalnız (eski GitHub OAuth
    çerezi, `sub` eklenmeden ÖNCE imzalanmış) oturumlar da burada 401 alır —
    Installation picker bir `user_id` GEREKTİRİR, `handle` yetmez; kullanıcı
    yeniden `/auth/login` ile giriş yaparsa (T-79 sonrası) çerez `sub` da
    taşır."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie or not settings.AUTH_SESSION_SECRET:
        raise HTTPException(status_code=401, detail="Oturum bulunamadı")
    try:
        payload = verify_session(settings.AUTH_SESSION_SECRET, cookie)
    except SessionSignatureError as exc:
        raise HTTPException(status_code=401, detail="Oturum geçersiz") from exc
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=401,
            detail="Bu işlem için oturumun bir kullanıcı kimliği taşıması gerekiyor "
            "— yeniden giriş yapın.",
        )
    return str(sub)


class AuthConfigResponse(BaseModel):
    enabled: bool
    # T-294: email+parola üyeliğinin AYRI ve BAĞIMSIZ kapısı — frontend bunu
    # okuyup "Kayıt Ol"/"E-posta ile gir" butonunu gösterip göstermeyeceğine
    # karar verir (GitHub butonundan bağımsız).
    email_enabled: bool


class AuthUserResponse(BaseModel):
    # T-294: `handle` artık İSTEĞE BAĞLI — email hesaplarının GitHub handle'ı
    # yok. GitHub oturumlarında dolu, email oturumlarında `None`; `email`
    # bunun simetriği (email oturumlarında dolu, GitHub oturumlarında `None`).
    handle: str | None = None
    avatar_url: str | None = None
    email: str | None = None


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class InstallUrlResponse(BaseModel):
    url: str


class RepoSummary(BaseModel):
    """T-79 — `GET /auth/installations` uç sözleşmesi (brifing, birebir)."""

    full_name: str
    private: bool


class InstallationSummary(BaseModel):
    installation_id: str
    account_login: str
    repos: list[RepoSummary]


class InstallationsResponse(BaseModel):
    installations: list[InstallationSummary]


class ReposResponse(BaseModel):
    """T-79 — `GET /auth/repos` uç sözleşmesi (brifing, birebir)."""

    selected: list[str]
    active: str | None = None
    demo: str | None = None


class ReposUpdateResponse(BaseModel):
    """T-79 — `PUT /auth/repos` uç sözleşmesi (brifing, birebir — `demo` YOK,
    yalnız `GET /auth/repos`'ta var)."""

    selected: list[str]
    active: str | None = None


class ReposUpdateRequest(BaseModel):
    repos: list[str]
    active: str | None = None


@router.get("/config")
def auth_config(settings: SettingsDep) -> AuthConfigResponse:
    # Sırlar yoksa da HER ZAMAN 200 — uygulama giriş yapılandırılmadan da
    # açılır (#79 kuralı); bu uç yalnız "giriş mümkün mü" sinyalini taşır.
    return AuthConfigResponse(
        enabled=settings.auth_enabled, email_enabled=settings.email_auth_enabled
    )


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
    session_factory: SessionFactoryDep,
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
    handle, avatar_url, github_user_id = fetch_github_user(access_token)
    # access_token burada biter — DB'ye/cache'e YAZILMAZ (#79 kuralı).

    # T-79: get-or-create — Installation picker'ın ihtiyaç duyduğu `user_id`
    # burada açılır/bulunur (bkz. store/identity_store.py docstring'i).
    with session_factory() as session:
        user = get_or_create_github_user(
            session, github_user_id=github_user_id, handle=handle, avatar_url=avatar_url
        )
        session.commit()
        user_id = user.id

    session_token = sign_session(
        settings.AUTH_SESSION_SECRET, handle=handle, avatar_url=avatar_url, sub=user_id
    )
    response = RedirectResponse(settings.AUTH_POST_LOGIN_URL, status_code=302)
    response.delete_cookie(STATE_COOKIE_NAME, **_cookie_kwargs(settings))
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=_SESSION_COOKIE_MAX_AGE_S,
        **_cookie_kwargs(settings),
    )
    return response


@router.post(
    "/register",
    status_code=201,
    responses={
        409: {"description": "Bu e-posta ile zaten bir hesap var"},
        422: {"description": "Parola politikası ya da e-posta biçimi ihlali"},
        429: {"description": "Çok fazla deneme"},
    },
)
def auth_register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
) -> AuthUserResponse:
    if not settings.email_auth_enabled:
        raise HTTPException(
            status_code=503,
            detail="E-posta ile üyelik yapılandırılmamış — AUTH_SESSION_SECRET eksik",
        )
    _enforce_auth_rate_limit(request)

    try:
        validate_password_policy(payload.password)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    normalized_email = normalize_email(payload.email)
    try:
        validate_email_format(normalized_email)
    except EmailFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    password_hash = hash_password(payload.password)
    with session_factory() as session:
        if get_user_by_email(session, normalized_email) is not None:
            raise HTTPException(status_code=409, detail="Bu e-posta ile zaten bir hesap var.")
        try:
            user = create_user(
                session, normalized_email=normalized_email, password_hash=password_hash
            )
            session.commit()
        except IntegrityError:
            # Yarış durumu: iki eşzamanlı istek aynı email'i AYNI ANDA
            # normalize edip yukarıdaki `get_user_by_email` kontrolünü
            # İKİSİ de geçebilir — DB'nin kendi UNIQUE kısıtı son savunma
            # hattı. Burada YUTULMAZ, 409'a çevrilir (sessiz fail-open değil).
            session.rollback()
            raise HTTPException(
                status_code=409, detail="Bu e-posta ile zaten bir hesap var."
            ) from None
        user_id = user.id
        user_email = user.email

    session_token = sign_session(settings.AUTH_SESSION_SECRET, sub=user_id, email=user_email)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=_SESSION_COOKIE_MAX_AGE_S,
        **_cookie_kwargs(settings),
    )
    return AuthUserResponse(handle=None, avatar_url=None, email=user_email)


@router.post(
    "/login",
    responses={
        401: {"description": "E-posta ya da parola hatalı"},
        429: {"description": "Çok fazla deneme"},
    },
)
def auth_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
) -> AuthUserResponse:
    if not settings.email_auth_enabled:
        raise HTTPException(
            status_code=503,
            detail="E-posta ile giriş yapılandırılmamış — AUTH_SESSION_SECRET eksik",
        )
    _enforce_auth_rate_limit(request)

    # Argon2 doğrulamasına GEÇMEDEN önce üst-sınır kontrolü (#294 brifingi
    # madde 4/DoS): aşırı uzun bir girdi hem sahte-hash hem gerçek-hash
    # dalında argon2'yi gereksiz yere yorar; politikaya zaten UYAMAYACAK bir
    # parola için bu iş hiç yapılmaz. Alt sınır BİLEREK burada uygulanmaz —
    # kısa bir parola zaten eşleşmeyecektir, erken-red hiçbir zamanlama
    # bilgisi sızdırmaz (DB'ye/hash'e hiç değmeden reddedilir).
    if len(payload.password) > MAX_PASSWORD_LENGTH:
        raise HTTPException(status_code=401, detail=_GENERIC_LOGIN_ERROR)

    normalized_email = normalize_email(payload.email)
    with session_factory() as session:
        user = get_user_by_email(session, normalized_email)
        password_hash = user.password_hash if user is not None else None
        # #294 brifingi madde 6: kullanıcı YOKSA da GERÇEK bir argon2
        # doğrulaması (sabit sahte hash'e karşı) çalıştırılır — "e-posta
        # bulunamadı" ile "parola yanlış" dallarının SÜRE PROFİLİ ayrışmasın
        # (kullanıcı-sayımı + zamanlama savunması). Aşağıdaki genel hata
        # İKİ durumda da AYNI: "bu email kayıtlı değil" gibi bir ayrım asla
        # döndürülmez.
        if not verify_password_or_dummy(password_hash, payload.password):
            raise HTTPException(status_code=401, detail=_GENERIC_LOGIN_ERROR)
        touch_last_login(session, user)
        session.commit()
        user_id = user.id
        user_email = user.email
        user_handle = user.github_handle
        user_avatar_url = user.avatar_url

    session_token = sign_session(
        settings.AUTH_SESSION_SECRET,
        sub=user_id,
        email=user_email,
        handle=user_handle,
        avatar_url=user_avatar_url,
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=_SESSION_COOKIE_MAX_AGE_S,
        **_cookie_kwargs(settings),
    )
    return AuthUserResponse(handle=user_handle, avatar_url=user_avatar_url, email=user_email)


@router.get("/me", responses={401: {"description": "Oturum yok/geçersiz"}})
def auth_me(request: Request, settings: SettingsDep) -> AuthUserResponse:
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie or not settings.AUTH_SESSION_SECRET:
        raise HTTPException(status_code=401, detail="Oturum bulunamadı")
    try:
        payload = verify_session(settings.AUTH_SESSION_SECRET, cookie)
    except SessionSignatureError as exc:
        raise HTTPException(status_code=401, detail="Oturum geçersiz") from exc
    # T-294: `.get()` — `payload["handle"]` DEĞİL. `handle` artık İSTEĞE
    # BAĞLI (email hesaplarının GitHub handle'ı yok); doğrudan indeksleme
    # email oturumlarında KeyError → 500'e sızardı (#62 dersinin ihlali).
    return AuthUserResponse(
        handle=payload.get("handle"),
        avatar_url=payload.get("avatar_url"),
        email=payload.get("email"),
    )


@router.post("/logout", status_code=204)
def auth_logout(settings: SettingsDep) -> Response:
    # Oturum olsun olmasın idempotent 204 — çıkış yapmak için giriş şart değil.
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE_NAME, **_cookie_kwargs(settings))
    return response


# --- Installation picker (T-79 — #79'un kalan dilimi) ---------------------
#
# Bu bölümdeki uçların HİÇBİRİ kalıcı bir GitHub token SAKLAMAZ: yalnızca
# `installation_id` (GitHub'ın verdiği, SIR OLMAYAN bir kimlik) DB'de kalır;
# repo listesi/erişim her ihtiyaç duyulduğunda `integrations/github/app_api.py`
# ile ANLIK bir installation-token'la CANLI GitHub'dan sorgulanır.


def _require_app_auth_enabled(settings: Settings) -> None:
    if not settings.app_auth_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "GitHub App kurulum akışı yapılandırılmamış — GITHUB_APP_ID/"
                "(GITHUB_APP_PRIVATE_KEY_PATH veya GITHUB_APP_PRIVATE_KEY)/"
                "AUTH_SESSION_SECRET eksik"
            ),
        )


@router.get(
    "/install-url",
    responses={401: {"description": "Oturum yok/geçersiz"}, 503: {"description": "Yapılandırılmamış"}},
)
def install_url(request: Request, settings: SettingsDep) -> InstallUrlResponse:
    """GitHub App kurulum sayfasının adresi — kullanıcı buraya yönlendirilir.

    Oturum ZORUNLU (`_require_session_user_id`): GitHub kuruluş sonrası
    `/auth/install-callback`'e dönerken bu oturumu kullanıp `installation_id`'yi
    HANGİ kullanıcıya bağlayacağını bilecek — oturumsuz başlatılan bir kurulum
    kimseye bağlanamaz (yetim installation_id, sessizce kaybolur)."""
    _require_app_auth_enabled(settings)
    _require_session_user_id(request, settings)
    slug = fetch_app_slug(settings)
    return InstallUrlResponse(url=f"https://github.com/apps/{slug}/installations/new")


@router.get("/install-callback", responses={401: {"description": "Oturum yok/geçersiz"}})
def install_callback(
    request: Request,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
    installation_id: str | None = None,
    setup_action: str | None = None,
) -> RedirectResponse:
    """GitHub'ın App kurulumu SONRASI yönlendirdiği uç (App ayarlarında
    "Setup URL" olarak bu adres kayıtlı olmalı — operasyonel bir GitHub App
    yapılandırma adımı, bu koddan YÖNETİLEMEZ; bkz. PR gövdesi "bilinen
    sınırlar").

    CSRF notu (bilinçli, dar kapsamlı kabul): bu uç bir TOKEN DEĞİŞTİRMEZ
    (OAuth `/callback`'in aksine `code`→`access_token` yok) — yalnızca
    GitHub'ın verdiği `installation_id`'yi oturumdaki kullanıcıya bağlar. En
    kötü senaryo bir saldırganın KENDİ (zaten kendisine ait) installation_id'sini
    kurbanın oturumuna bağlatması — kurbanın verisi SIZMAZ, yalnızca saldırganın
    reposu kurbanın "izlenebilir" setine girer (kurban `PUT /auth/repos`'a
    kadar hiçbir şey görmez). Bu düşük-önem sınır PR gövdesinde açıkça notlanır.
    """
    if setup_action == "install" and installation_id:
        user_id = _require_session_user_id(request, settings)
        repos = fetch_installation_repositories(settings, installation_id)
        account_login = ""
        if repos:
            owner = repos[0].get("owner") or {}
            account_login = str(owner.get("login") or "")
        with session_factory() as session:
            upsert_installation(
                session,
                installation_id=installation_id,
                account_login=account_login,
                user_id=user_id,
            )
            session.commit()
    else:
        logger.info(
            "install-callback: installation_id yok ya da setup_action=%s (kurulum tamamlanmadı/iptal)",
            setup_action,
        )
    return RedirectResponse(settings.AUTH_POST_LOGIN_URL, status_code=302)


@router.get("/installations", responses={401: {"description": "Oturum yok/geçersiz"}})
def list_installations(
    request: Request, settings: SettingsDep, session_factory: SessionFactoryDep
) -> InstallationsResponse:
    """Kullanıcının App kurulumları + her birinin erişebildiği repolar.
    Token ANLIK üretilir (integrations/github/app_api.py), hiçbir yerde
    saklanmaz."""
    _require_app_auth_enabled(settings)
    user_id = _require_session_user_id(request, settings)

    with session_factory() as session:
        installations = list_installations_for_user(session, user_id)

    summaries: list[InstallationSummary] = []
    for installation in installations:
        repos = fetch_installation_repositories(settings, installation.installation_id)
        summaries.append(
            InstallationSummary(
                installation_id=installation.installation_id,
                account_login=installation.account_login,
                repos=[
                    RepoSummary(full_name=str(r.get("full_name")), private=bool(r.get("private")))
                    for r in repos
                    if r.get("full_name")
                ],
            )
        )
    return InstallationsResponse(installations=summaries)


@router.get("/repos", responses={401: {"description": "Oturum yok/geçersiz"}})
def get_repos(
    request: Request, settings: SettingsDep, session_factory: SessionFactoryDep
) -> ReposResponse:
    user_id = _require_session_user_id(request, settings)
    with session_factory() as session:
        user = get_user_by_id(session, user_id)
        watched = list_watched_repos(session, user_id)
    return ReposResponse(
        selected=[row.repo_full_name for row in watched],
        active=user.active_repo_full_name if user is not None else None,
        demo=settings.demo_repo_full_name,
    )


@router.put(
    "/repos",
    responses={401: {"description": "Oturum yok/geçersiz"}, 403: {"description": "İzinsiz repo"}},
)
def update_repos(
    payload: ReposUpdateRequest,
    request: Request,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
) -> ReposUpdateResponse:
    """Verilen `repos` kullanıcının GERÇEKTEN erişebildiği bir kurulumda
    OLMALI — her biri CANLI GitHub'dan (bu kullanıcının installation'ları
    üzerinden) doğrulanır; değilse 403 (istemcinin gönderdiği repo'ya asla
    körlemesine güvenilmez — T-79 brifinginin en kritik kuralı)."""
    _require_app_auth_enabled(settings)
    user_id = _require_session_user_id(request, settings)

    with session_factory() as session:
        installations = list_installations_for_user(session, user_id)

    # Bu kullanıcının HERHANGİ bir kurulumu üzerinden erişebildiği
    # repo_full_name -> installation_id eşlemesi — CANLI GitHub'dan.
    accessible: dict[str, str] = {}
    for installation in installations:
        for repo in fetch_installation_repositories(settings, installation.installation_id):
            full_name = repo.get("full_name")
            if full_name:
                accessible[str(full_name)] = installation.installation_id

    unauthorized = [repo for repo in payload.repos if repo not in accessible]
    if unauthorized:
        raise HTTPException(
            status_code=403,
            detail=f"Şu repolara erişiminiz yok (kurulumlarınızda değil): {unauthorized}",
        )
    if payload.active is not None and payload.active not in payload.repos:
        raise HTTPException(
            status_code=403, detail="active, repos listesinin bir üyesi olmalı."
        )

    with session_factory() as session:
        user = get_user_by_id(session, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Oturum bulunamadı")
        replace_watched_repos(
            session,
            user_id=user_id,
            repos=[(repo, accessible[repo]) for repo in payload.repos],
        )
        set_active_repo(session, user, payload.active)
        session.commit()

    return ReposUpdateResponse(selected=list(payload.repos), active=payload.active)
