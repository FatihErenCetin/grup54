from collections import OrderedDict
from collections.abc import Callable
from typing import Any

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

    _DEFAULT_MAX_CACHE_ENTRIES = 500

    def __init__(
        self,
        token_provider: Callable[[], str],
        http_client: httpx.Client | None = None,
        max_cache_entries: int = _DEFAULT_MAX_CACHE_ENTRIES,
    ):
        if max_cache_entries <= 0:
            raise ValueError("max_cache_entries must be positive")
        self._token_provider = token_provider
        self._http = http_client or httpx.Client(timeout=15.0)
        self._max_cache_entries = max_cache_entries
        # Poll'lar zamanla degisen anahtarlar uretir (orn. cache_key=f"commits:{since_iso}")
        # - sinirsiz buyumeyi onlemek icin ikisi birlikte LRU tahliye edilir.
        self._etags: OrderedDict[str, str] = OrderedDict()
        self._last_body: OrderedDict[str, Any] = OrderedDict()

    def get(self, path: str, *, params: dict | None = None, cache_key: str | None = None):
        """304 donerse son bilinen govdeyi replay eder (degisiklik yok, veri
        kaybolmaz). Hic govde gormemisken 304 gelirse (beklenmedik sunucu
        davranisi) None doner. Aksi halde parse edilmis JSON."""
        key = cache_key or path
        headers = {
            "Authorization": f"Bearer {self._token_provider()}",
            "Accept": "application/vnd.github+json",
        }
        if key in self._etags:
            headers["If-None-Match"] = self._etags[key]

        resp = self._http.get(f"{_BASE}{path}", params=params, headers=headers)
        if resp.status_code == 304:
            return self._last_body.get(key)
        raise_for_status(resp)

        body = resp.json()
        etag = resp.headers.get("ETag")
        if etag:
            self._remember(key, etag, body)
        return body

    def _remember(self, key: str, etag: str, body: Any) -> None:
        self._etags[key] = etag
        self._etags.move_to_end(key)
        self._last_body[key] = body
        self._last_body.move_to_end(key)
        while len(self._etags) > self._max_cache_entries:
            oldest_key, _ = self._etags.popitem(last=False)
            self._last_body.pop(oldest_key, None)
