"""Hosted demo IP/rate cap (#63) — yalnız `DEMO_MODE=true` iken app.py tarafından
takılır (bkz. app.py::create_app). local/dev'de bu modül hiç devreye girmez.

Üç parça:
- `WindowCounter`: saf, framework'süz kayan-pencere sayacı (`time_fn` enjekte
  edilebilir → testte `sleep` yok). Anahtar sayısı da sınırlı (`max_keys`,
  LRU tahliye) — aksi halde IP-flood'u bellek DoS'una dönerdi.
- `client_ip`: Fly proxy arkasında `request.client.host` proxy'nin İÇ IP'sidir;
  başlığı okumazsak TÜM trafik tek kovaya düşer ve cap herkesi birlikte keser.
  Öncelik: `Fly-Client-IP` > `X-Forwarded-For` ilk kayıt > `request.client.host`.
- `DemoRateLimitMiddleware`: `/query` + `/scope/check` (kullanıcı-girdili, AI
  çağıran yollar) ayrı ve daha sıkı bir "AI kovası"nda; geri kalan GET'ler genel
  kovada. `/radar` BİLEREK genel kovada (frontend 10 sn'de bir poll'luyor; AI
  kovasına konsaydı demonun kendi Radar sayfasını keserdi — maliyetini asıl
  cached-verdict katmanı sıfırlıyor, bkz. engine/cache.py).

⚠️ IP başlığı istemci tarafından uydurulabilir → per-IP cap atlatılabilir.
Kabul edilen risk: bu bir MALİYET KAPAĞI, güvenlik sınırı değil; uydurmaya
karşı asıl koruma AI kovasındaki GLOBAL tavandır (`DEMO_AI_GLOBAL_LIMIT`).
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ensemble.api.errors import ErrorEnvelope
from ensemble.config import Settings

# Kullanıcı-girdili, gerçekten AI (Gemini judge/embed) çağıran GET yolları
# (Ek D docs/sprint3-kontratlar.md): ScopeService.check_scope embed+judge
# çağırıyor; get_current_scope/list_verdicts hiç AI çağırmıyor (ayrı kova
# gerektirmez, genel kovaya düşer).
AI_METERED_PATHS = frozenset({"/query", "/scope/check"})

# Fly health-check bunu 30 sn'de bir vurur (fly.toml) — asla limitlenmez,
# yoksa makine unhealthy işaretlenir.
_EXEMPT_PATHS = frozenset({"/health"})

_GLOBAL_KEY = "*"


class WindowCounter:
    """Saf kayan-pencere istek sayacı — framework bağımlılığı yok."""

    def __init__(
        self,
        window_s: float,
        *,
        max_keys: int = 5000,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if window_s <= 0:
            raise ValueError("window_s must be positive")
        if max_keys <= 0:
            raise ValueError("max_keys must be positive")
        self._window_s = float(window_s)
        self._max_keys = max_keys
        self._time_fn = time_fn
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    def allow(self, key: str, limit: int) -> tuple[bool, int]:
        """`(izin_verildi, retry_after_saniye)`. Reddedilen istek pencereyi
        İLERLETMEZ (sayaca eklenmez) — retry fırtınası kendi kendini beslemez."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        now = self._time_fn()
        cutoff = now - self._window_s
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
            else:
                self._hits.move_to_end(key)

            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= limit:
                retry_after = max(1, math.ceil(hits[0] + self._window_s - now))
                return False, retry_after

            hits.append(now)
            self._evict_overflow()
            return True, 0

    def _evict_overflow(self) -> None:
        while len(self._hits) > self._max_keys:
            self._hits.popitem(last=False)  # en eski (LRU) anahtarı at

    def __len__(self) -> int:
        return len(self._hits)


def client_ip(request: Request) -> str:
    fly_ip = request.headers.get("fly-client-ip")
    if fly_ip and fly_ip.strip():
        return fly_ip.strip()

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def _rate_limited_response(retry_after: int) -> JSONResponse:
    body = ErrorEnvelope(
        error="demo_rate_limited",
        message="Demo istek limiti aşıldı — birazdan tekrar deneyin.",
        status=429,
    )
    return JSONResponse(
        status_code=429,
        content=body.model_dump(),
        headers={"Retry-After": str(max(1, int(retry_after)))},
    )


class DemoRateLimitMiddleware(BaseHTTPMiddleware):
    """Yalnız `DEMO_MODE=true` iken `create_app`'e takılır (app.py). CORS
    MIDDLEWARE'İNDEN ÖNCE eklenmesi ZORUNLU — Starlette `add_middleware`'i
    başa ekler (son eklenen en dışta koşar); bu middleware CORS'tan SONRA
    eklenirse 429 cevabı CORS katmanının dışında üretilir ve tarayıcı gerçek
    hatayı "CORS error" diye gizler (#45/#150 dersi). Sıra `test_demo_rate_limit.py`
    ile kilitli.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(app)
        self._settings = settings
        self._ai_counter = WindowCounter(settings.DEMO_RATE_WINDOW_S, time_fn=time_fn)
        self._general_counter = WindowCounter(settings.DEMO_RATE_WINDOW_S, time_fn=time_fn)

    async def dispatch(self, request: Request, call_next):
        if request.method != "GET" or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        ip = client_ip(request)

        if request.url.path in AI_METERED_PATHS:
            allowed_ip, retry_ip = self._ai_counter.allow(ip, self._settings.DEMO_AI_RATE_LIMIT)
            if not allowed_ip:
                return _rate_limited_response(retry_ip)
            allowed_global, retry_global = self._ai_counter.allow(
                _GLOBAL_KEY, self._settings.DEMO_AI_GLOBAL_LIMIT
            )
            if not allowed_global:
                return _rate_limited_response(retry_global)
            return await call_next(request)

        allowed, retry_after = self._general_counter.allow(ip, self._settings.DEMO_RATE_LIMIT)
        if not allowed:
            return _rate_limited_response(retry_after)
        return await call_next(request)
