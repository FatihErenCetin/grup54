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
karşı asıl koruma GLOBAL tavandır.

G6 düzeltmesi — genel kovada da GLOBAL tavan: `/radar` (Gemini judge +
embeddings çağıran) genel kovada olduğu için eskiden yalnız IP-başına
(`DEMO_RATE_LIMIT`) sınırlıydı; sahte `Fly-Client-IP` rotasyonuyla bu sınır
sonsuz kez atlatılabiliyordu (ölçüm: 2000 istek / 2000 uydurma IP → 200=2000,
429=0 — fatura kapağı fiilen yoktu). AI kovasına taşımadık (docs/sprint3-
kontratlar.md Ek F/F2 BİLEREK `/radar`'ı genel kovada tutuyor — frontend'in
kendi 10 sn pollu, AI kovasının çok daha sıkı per-IP/global bütçesini
paylaşırsa kesilirdi). Bunun yerine AI kovasının zaten donmuş per-IP:global
oranı (`DEMO_AI_RATE_LIMIT` : `DEMO_AI_GLOBAL_LIMIT`, varsayılan 10:60 = 6x)
genel kovaya da uygulanır — YENİ bir `.env` anahtarı EKLENMEDEN, tamamen
mevcut `DEMO_*` ayarlarından TÜRETİLİR (bkz. `_general_global_limit`).
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

# #340: onboarding sihirbazının GERÇEKTEN LLM çağıran iki ucu. POST oldukları
# için yukarıdaki GET kovasına düşmüyorlardı — bu liste olmadan hosted demoda
# tamamen SINIRSIZ kalırlardı (kullanıcı-girdili serbest metin + Gemini çağrısı
# = doğrudan fatura). Sihirbazın diğer uçları (`/onboarding/sorular`, `/plan`,
# `/durum`) deterministik ve ağsızdır; buraya BİLEREK alınmadı. `/onboarding/
# uygula` da yok — o zaten hosted'da 404 (yazma yalnız local).
AI_METERED_POST_PATHS = frozenset({"/onboarding/brief", "/onboarding/taslak"})

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
        # G6: genel kovanın da bir GLOBAL tavanı olsun (IP rotasyonuna karşı) -
        # ama AI kovası için donmuş ayrı bir env EKLEMEDEN (docs/sprint3-
        # kontratlar.md Ek F kapsamında degil). AI kovasının zaten seçilmiş
        # per-IP:global oranını (varsayılan 10:60 = 6x) genel kovaya da
        # uygularız: mevcut üç DEMO_* değerinden türetilir, yeni ayar yok.
        self._general_global_limit = max(
            1,
            round(
                settings.DEMO_RATE_LIMIT
                * settings.DEMO_AI_GLOBAL_LIMIT
                / settings.DEMO_AI_RATE_LIMIT
            ),
        )

    async def dispatch(self, request: Request, call_next):
        # POST'lar kural olarak ölçülmez (webhook/auth gibi uçlar kendi
        # korumasını taşır); TEK istisna AI çağıran onboarding uçlarıdır —
        # aksi halde LLM maliyeti kapaksız kalırdı (#340).
        ai_post = (
            request.method == "POST" and request.url.path in AI_METERED_POST_PATHS
        )
        if (request.method != "GET" and not ai_post) or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        ip = client_ip(request)

        if ai_post or request.url.path in AI_METERED_PATHS:
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

        # G6: IP başlığı uydurularak per-IP kapağı atlatılsa bile (rotasyon),
        # aynı `_general_counter` üzerinde tutulan "*" global anahtarı toplam
        # trafiği pencere başına sınırlar (AI kovasındaki desenin aynısı).
        allowed_global, retry_global = self._general_counter.allow(
            _GLOBAL_KEY, self._general_global_limit
        )
        if not allowed_global:
            return _rate_limited_response(retry_global)
        return await call_next(request)
