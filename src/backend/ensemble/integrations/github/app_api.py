"""GitHub App yönetim API'leri (T-79 — çok-kiracılı repo seçimi / Installation
picker). `integrations/github/auth.py::InstallationTokenCache`'İ KARIŞTIRMA:
o modül TEK, SABİT bir `installation_id` (`.env`'deki, ingest için) etrafında
kurulu ve token'ı CACHE'LER; bu modülün fonksiyonları ARBİTRER bir
`installation_id` için HER ÇAĞRIDA anlık token üretir, SAKLAMAZ (#79 kuralı:
"token anlık üretilir, saklanmaz" — yalnızca `installation_id`, kalıcı ama
SIR OLMAYAN bir kimlik, `installations` tablosunda saklanır).

Kullanım yeri: `api/routers/auth.py` (`/auth/install-url`, `/auth/installations`,
`PUT /auth/repos` — kullanıcının installation'ları üzerinden erişebildiği
repoları CANLI GitHub'dan sorgular, hiçbir yerde önbelleklenmiş bir repo
listesi TUTMAZ).
"""

from __future__ import annotations

import httpx

from ensemble.config import Settings
from ensemble.integrations.github.auth import build_app_jwt
from ensemble.integrations.github.client import raise_for_status
from ensemble.integrations.github.errors import GitHubConfigError

APP_URL = "https://api.github.com/app"
INSTALLATION_TOKEN_URL = "https://api.github.com/app/installations/{installation_id}/access_tokens"
INSTALLATION_REPOS_URL = "https://api.github.com/installation/repositories"

_APP_HEADERS = {"Accept": "application/vnd.github+json"}
# GitHub'ın "sonsuz" bir kurulumu olmadığı için sayfalama tavanı — tek bir
# istekte 100*_MAX_PAGES'ten fazla repo listelemeyi reddeder (savunma amaçlı
# üst sınır; adapter.py::_sayfali'nin GITHUB_BACKFILL_LIMIT tavanıyla AYNI
# disiplin, burada sabit çünkü kullanıcı-anlık bir uç, ayarlanabilir bir
# .env anahtarı GEREKTİRMEZ).
_MAX_PAGES = 10


def fetch_app_slug(settings: Settings, *, http_client: httpx.Client | None = None) -> str:
    """`GET /app` — App'in KENDİSİ hakkında meta veri (slug dahil). Install-url
    (`https://github.com/apps/<slug>/installations/new`) için gerekli; `slug`
    `.env`'de AYRICA saklanmaz (bir ayar DEĞİL, App JWT ile HER ihtiyaç
    duyulduğunda sorgulanan salt-okunur bir GERÇEK)."""
    app_jwt = build_app_jwt(settings)
    http = http_client or httpx.Client(timeout=15.0)
    resp = http.get(APP_URL, headers={**_APP_HEADERS, "Authorization": f"Bearer {app_jwt}"})
    raise_for_status(resp)
    body = resp.json()
    slug = body.get("slug")
    if not slug:
        raise GitHubConfigError("GitHub /app yanıtında 'slug' yok")
    return str(slug)


def fetch_installation_token(
    settings: Settings, installation_id: str, *, http_client: httpx.Client | None = None
) -> str:
    """Verilen `installation_id` için ANLIK bir installation access token
    üretir — `InstallationTokenCache`'in AKSİNE hiçbir yerde SAKLAMAZ/
    CACHE'LEMEZ (çağıran kullanıp atar)."""
    app_jwt = build_app_jwt(settings)
    http = http_client or httpx.Client(timeout=15.0)
    resp = http.post(
        INSTALLATION_TOKEN_URL.format(installation_id=installation_id),
        headers={**_APP_HEADERS, "Authorization": f"Bearer {app_jwt}"},
    )
    raise_for_status(resp)
    token = resp.json().get("token")
    if not token:
        raise GitHubConfigError("GitHub installation-token yanıtında 'token' yok")
    return str(token)


def fetch_installation_repositories(
    settings: Settings, installation_id: str, *, http_client: httpx.Client | None = None
) -> list[dict]:
    """`GET /installation/repositories` — bu kurulumun ERİŞEBİLDİĞİ repo
    listesi (installation-token ile, kullanıcı-token'ı GEREKMEZ). Token bu
    çağrı için üretilir, dönerken atılır."""
    token = fetch_installation_token(settings, installation_id, http_client=http_client)
    http = http_client or httpx.Client(timeout=15.0)
    headers = {**_APP_HEADERS, "Authorization": f"Bearer {token}"}

    repos: list[dict] = []
    for page in range(1, _MAX_PAGES + 1):
        resp = http.get(
            INSTALLATION_REPOS_URL, headers=headers, params={"per_page": 100, "page": page}
        )
        raise_for_status(resp)
        body = resp.json()
        page_repos = body.get("repositories") or []
        repos.extend(page_repos)
        if len(page_repos) < 100:
            break
    return repos
