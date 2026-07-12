from collections.abc import Callable

import httpx

from ensemble.integrations.github.errors import (
    GitHubAuthError,
    GitHubError,
    GitHubRateLimitError,
    GitHubTransientError,
)

_BASE = "https://api.github.com"


def raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    if resp.status_code == 401:
        raise GitHubAuthError(f"401 yetkisiz: {resp.text}")
    if resp.status_code == 403:
        if resp.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubRateLimitError(f"rate limit doldu: {resp.headers.get('X-RateLimit-Reset')}")
        raise GitHubAuthError(f"403 izin hatasi: {resp.text}")
    if resp.status_code == 429:
        raise GitHubRateLimitError(f"429 secondary rate limit: {resp.headers.get('Retry-After')}")
    if resp.status_code >= 500:
        raise GitHubTransientError(f"{resp.status_code} sunucu hatasi: {resp.text}")
    raise GitHubError(f"{resp.status_code} beklenmeyen hata: {resp.text}")


class GitHubRestClient:
    """ETag-aware dusuk seviye GitHub REST istemcisi.

    Prompt/normalize mantigi tasimaz - tek islevi yetkilendirilmis, rate-limit
    dostu (If-None-Match) bir GET yapmak. Ust katman (adapter.py) bunu kullanir.
    """

    def __init__(self, token_provider: Callable[[], str], http_client: httpx.Client | None = None):
        self._token_provider = token_provider
        self._http = http_client or httpx.Client(timeout=15.0)
        self._etags: dict[str, str] = {}

    def get(self, path: str, *, params: dict | None = None, cache_key: str | None = None):
        """304 donerse None (degisiklik yok). Aksi halde parse edilmis JSON."""
        key = cache_key or path
        headers = {
            "Authorization": f"Bearer {self._token_provider()}",
            "Accept": "application/vnd.github+json",
        }
        if key in self._etags:
            headers["If-None-Match"] = self._etags[key]

        resp = self._http.get(f"{_BASE}{path}", params=params, headers=headers)
        if resp.status_code == 304:
            return None
        raise_for_status(resp)

        etag = resp.headers.get("ETag")
        if etag:
            self._etags[key] = etag
        return resp.json()
