"""GitHub App KULLANICI yetkilendirme akışı (OAuth, #79 daraltılmış dilim).

BUNU `auth.py::InstallationTokenCache` ile KARIŞTIRMA: o modül App'in
KENDİSİ adına (machine auth, ingest) `installation access token` üretir; bu
modül ise "bu tarayıcı oturumunun ARKASINDAKİ GitHub kullanıcısı kim"
sorusuna cevap verir (kullanıcı girişi — #79 kuralı gereği yalnız "kim
olduğunu göster" katmanı, hiçbir mevcut uç bu akışa bağımlı DEĞİL).

`access_token` bu akışta HİÇBİR YERDE SAKLANMAZ (ne DB ne cache) — yalnız
`fetch_github_user` çağrısı için bellekte tutulur, sonra atılır (#79'un kendi
kuralı; kullanıcı/identity tablosu = #79'un AYRI, kalan dilimi).
"""

from urllib.parse import urlencode

import httpx

from ensemble.config import Settings
from ensemble.integrations.github.client import raise_for_status
from ensemble.integrations.github.errors import GitHubAuthError

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"


def build_authorize_url(settings: Settings, *, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(
    settings: Settings,
    *,
    code: str,
    redirect_uri: str,
    http_client: httpx.Client | None = None,
) -> str:
    """`code`'u access token'a çevirir. GitHub bu uçta reddi de 200 status
    ile ama gövdede `error` alanıyla bildirir (HTTP hata kodu DEĞİL) — bu
    yüzden `raise_for_status`'tan SONRA ayrıca gövde kontrolü şart."""
    http = http_client or httpx.Client(timeout=15.0)
    resp = http.post(
        TOKEN_URL,
        data={
            "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
            "client_secret": settings.GITHUB_OAUTH_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"Accept": "application/json"},
    )
    raise_for_status(resp)
    body = resp.json()
    if "error" in body:
        # client_secret bu govdeye HİÇ girmez (GitHub'ın kendi yanıtı) —
        # yalnız GitHub'ın ürettiği error_description yansıtılır, iç detay
        # sızmaz (errors.py disiplinine uyumlu).
        raise GitHubAuthError(
            f"GitHub OAuth reddetti: {body.get('error_description', body['error'])}"
        )
    access_token = body.get("access_token")
    if not access_token:
        raise GitHubAuthError("GitHub OAuth yanıtında access_token yok")
    return access_token


def fetch_github_user(
    access_token: str, *, http_client: httpx.Client | None = None
) -> tuple[str, str | None]:
    """`(handle, avatar_url)` — token burada kullanılıp ATILIR, saklanmaz."""
    http = http_client or httpx.Client(timeout=15.0)
    resp = http.get(
        USER_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
    )
    raise_for_status(resp)
    body = resp.json()
    return body["login"], body.get("avatar_url")
