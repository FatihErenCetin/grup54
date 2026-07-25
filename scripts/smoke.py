"""Deploy-sonrası canlı smoke testi (#189) — yalnız stdlib, bağımlılık YOK.

Bir Fly (backend) + Vercel (frontend) deploy'unun **gerçekten** ayakta ve
doğru bağlı olduğunu kanıtlar: `/health` + readiness (#53) + CORS
(`CORS_ORIGINS` ↔ `VITE_API_BASE_URL` çift-yön kilidi, S3 Ek A2) + 6 SPA
route'unun doğrudan+refresh deep-link'i (Vercel rewrite kanıtı, S3 Ek E).

Kod içi hiçbir yeni bağımlılık eklenmez (yalnız `json/os/sys/time/urllib/
dataclasses`) → `uv.lock` bu PR'da dokunulmaz. `uv run python scripts/
smoke.py` ya da düz `python3 scripts/smoke.py` ile çalışır.

Kabul kriterlerinin kaynağı: GitHub issue #189 + `docs/sprint3-kontratlar.md`
Ek A (env eşlemesi) / Ek B (router imzaları) / Ek E (frontend tüketim
haritası). `/health` bugün `ready: bool` DÖNMÜYOR (#53 kapandı ama boolean
readiness alanı eklemedi) — bu script o boşluğu **kapatmaz**, mevcut 4
alandan (`status/mode/github_auth/gemini`) readiness'i **türetir**. `/health`
gövdesine alan eklemek S3 Ek A/B FROZEN kontratını ve openapi drift-check'i
kırar; o yüzden endpoint'e DOKUNULMAZ.

Env sözleşmesi:
    SMOKE_API_URL   zorunlu.  Backend base URL (örn. https://<app>.fly.dev).
    SMOKE_WEB_URL    opsiyonel. Frontend base URL (örn. https://<app>.vercel.app).
                     Verilmezse CORS + SPA route blokları ATLANIR (yalnız
                     /health kontrol edilir) — çıktıda büyük bir WARN + "kısmi
                     smoke" etiketiyle işaretlenir.
    SMOKE_STRICT     github_auth/gemini "missing" olduğunda FAIL mi WARN mi
                     verileceğini override eder. **Varsayılan AÇIK (fail-safe):**
                     yalnızca açıkça KAPATAN değerler ("0"/"false"/"no"/"off",
                     büyük/küçük harf duyarsız) strict'i kapatır; "1"/"true"/
                     "yes"/"on" ve tanınmayan her değer strict'i AÇIK bırakır
                     (eski hata: yalnız tam "1" strict sayılıyordu — operatör
                     `SMOKE_STRICT=true` yazınca sessizce non-strict'e
                     düşüyordu). Tanımsız/boş bırakılırsa `mode == "hosted"`
                     iken otomatik strict (canlıda secret'lar İSTENİR —
                     Sprint-3 Ek A "canlıda İSTENMEZ" kuralının makine hâli),
                     `mode == "local"` iken degrade (WARN) — geliştirici Fake
                     adapter'larla yeşil kalır.
    SMOKE_TIMEOUT_S  saniye, varsayılan 15.
    SMOKE_RETRIES    varsayılan 2 — yalnız İLK `/health` denemesi için (Fly
                     `auto_stop_machines="stop"` soğuk başlangıcı; CORS/SPA
                     istekleri retry'sız).

Kullanım:
    make smoke SMOKE_API_URL=https://ensemble-api.fly.dev \\
               SMOKE_WEB_URL=https://ensemble.vercel.app
    # ya da doğrudan:
    SMOKE_API_URL=... SMOKE_WEB_URL=... uv run python scripts/smoke.py

Çıkış kodu:
    0 → tüm kontroller (ya da atlanmışsa yalnız /health) yeşil.
    1 → en az bir FAIL var (non-2xx / eksik-yanlış readiness / eksik-yanlış
        CORS / SPA route kırık) — kullanım hatası (env eksik) de 1 döner.

Tüm satırlar TEK akışa (stdout) yazılır; yalnız kullanım hatası (env eksik)
stderr'e gider. Test dosyası: `tests/unit/test_smoke.py` (urllib mock'lanmaz —
`main()`'e sahte transport enjekte edilir, gerçek karar mantığı koşar).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Mapping
from urllib.parse import urlsplit

# 6 SPA route'u — src/frontend/src/main.tsx <Routes> ile BİREBİR OLMALI.
# DÜZELTME (B1): önceki yorum "route listesi burada sessizce kısalırsa
# test #15 yakalar" derdi — bu YANLIŞ. test #15
# (test_alti_route_iki_gecis_isteniyor) beklentilerini BU tuple'ın
# kendisinden türetiyor (`for route in ROUTES: ...`), yani ROUTES burada
# kısalır/genişler/yeniden sıralanırsa test kendi kendine göre hâlâ geçer
# (self-referans → tautoloji, gerçek bir regresyon kilidi DEĞİL). Asıl kilit
# `tests/unit/test_smoke.py::test_routes_sabit_liste_ile_esit` — literal
# (hardcode) 6 route'a karşı karşılaştırır; main.tsx <Routes> ile burası
# birbirinden sessizce sapıyorsa YALNIZCA o test kırılır.
ROUTES: tuple[str, ...] = ("/", "/board", "/scope", "/graph", "/activity", "/ask")

# src/frontend/index.html'deki kök düğüm — "200 ama gerçekten index.html mi"
# kanıtı (Vercel yanlış-proje/placeholder vakası: 200 dönebilir ama SPA değil).
HTML_MARKER = 'id="root"'

DEFAULT_TIMEOUT_S = 15.0
DEFAULT_RETRIES = 2
# Soğuk başlangıç retry'ları arasında beklenen süre (yalnız ilk /health denemesi).
RETRY_DELAY_S = 2.0

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_REDIRECT_STATUSES = frozenset({300, 301, 302, 303, 307, 308})


@dataclass
class Response:
    """HTTP cevabının transport-bağımsız hâli — `http_fetch` VE testteki
    `FakeTransport` aynı şekli üretir (main() ikisini de ayırt etmez)."""

    status: int  # 0 = bağlantı hiç kurulamadı (timeout/DNS/refused)
    headers: dict[str, str]  # anahtarlar KÜÇÜK harf (case-insensitive lookup)
    body: str

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


@dataclass
class Report:
    """Tek akışlı rapor: satırlar sırayla biriktirilir, failures/warnings
    ayrı listelerde tutulur (main() `failures` boş değilse exit 1 döner)."""

    lines: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self, msg: str) -> None:
        self.lines.append(f"OK   {msg}")

    def warn(self, msg: str) -> None:
        self.lines.append(f"WARN {msg}")
        self.warnings.append(msg)

    def fail(self, msg: str) -> None:
        self.lines.append(f"FAIL {msg}")
        self.failures.append(msg)


def normalize_base(url: str) -> str:
    """Sondaki `/` kırpılır → `{base}/health` her zaman `//health` DEĞİL."""
    return url.rstrip("/")


def origin_of(url: str) -> str:
    """`scheme://host[:port]` — path/query/hash düşer (CORS Origin başlığı)."""
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_local_host(url: str) -> bool:
    return (urlsplit(url).hostname or "") in _LOCAL_HOSTS


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """`redirect_request()` None dönünce `HTTPRedirectHandler` "ele almadım"
    sayılır → zincir `HTTPDefaultErrorHandler`'a düşer ve 3xx'i `HTTPError`
    olarak fırlatır (aşağıdaki `except urllib.error.HTTPError` dalı bunu
    `Response(status=3xx)` yapar). `allow_redirects=False`'in çekirdeği."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


# Tek sefer inşa edilir (build_opener maliyeti) — `_NoRedirectHandler`
# `HTTPRedirectHandler`'ın alt sınıfı olduğu için `build_opener` varsayılan
# redirect-izleyen handler'ı BUNUNLA değiştirir (stdlib sözleşmesi).
_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def http_fetch(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    allow_redirects: bool = True,
) -> Response:
    """Gerçek ağ transportu (stdlib urllib). Hiçbir zaman raise etmez —
    `HTTPError` (4xx/5xx) bir `Response`'a çevrilir; `URLError`/timeout/DNS
    hatası `Response(status=0, body="<tip>: <mesaj>")` olur (traceback yerine
    tek satır FAIL — main() akışı hiç kesilmez).

    `allow_redirects=False` (varsayılan `True`) → 3xx cevabı SESSİZCE izlenip
    hedefe (örn. `index.html`) varılmaz; 3xx'in kendisi `Response(status=3xx,
    headers={"location": ...})` olarak döner. #189 blocker'ı: `urlopen`
    GET için 3xx'i varsayılan olarak izler — SPA route kontrolü (K2) deep-link'in
    DOĞRUDAN servis edildiğini kanıtlamalı, redirect sonrası index.html'e
    varılmasını değil (bkz. `check_spa_routes`)."""
    req = urllib.request.Request(url, method=method, headers=dict(headers or {}))
    opener_open = urllib.request.urlopen if allow_redirects else _NO_REDIRECT_OPENER.open
    try:
        with opener_open(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return Response(status=resp.status, headers=hdrs, body=body)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - savunma
            body = ""
        hdrs = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
        return Response(status=exc.code, headers=hdrs, body=body)
    except Exception as exc:  # URLError, socket timeout, ConnectionRefusedError...
        return Response(status=0, headers={}, body=f"{type(exc).__name__}: {exc}")


# `allow_redirects` `http_fetch` imzasında keyword-only (varsayılan True);
# testteki `FakeTransport.__call__` de aynı imzayı taşır (bkz. test_smoke.py).
FetchFn = Callable[..., Response]


def _call(fetch: FetchFn, url: str, **kwargs: object) -> Response:
    """`fetch(...)` çağrısını sarar: gerçek `http_fetch` zaten hiç raise
    etmez ama testteki `FakeTransport` bilinçli olarak `URLError` fırlatma
    seçeneği taşıyabilir (bağlantı-yok senaryosu) — burada tek noktadan
    yakalanır ki traceback hiçbir çağıran fonksiyonu kesmesin."""
    try:
        return fetch(url, **kwargs)
    except Exception as exc:  # pragma: no cover - normal yol http_fetch'te yakalanır
        return Response(status=0, headers={}, body=f"{type(exc).__name__}: {exc}")


def check_http_scheme(url: str, label: str, rep: Report) -> bool:
    """localhost/127.0.0.1/::1 DIŞINDA `http://` kabul etmez (Fly
    `force_https=true` → `http://` verilirse urllib OPTIONS'ta 301'i sessizce
    izlemeyip `HTTPError` fırlatır; bu kafa karıştırıcı hatayı önceden,
    anlamlı bir mesajla önler)."""
    parsed = urlsplit(url)
    if parsed.scheme == "http" and not _is_local_host(url):
        rep.fail(
            f"{label}: http:// şeması canlı hostta desteklenmez "
            f"(https:// ver — Fly force_https urllib'i kırar): {url}"
        )
        return False
    return True


def check_health(
    api: str,
    rep: Report,
    fetch: FetchFn,
    *,
    strict_override: bool | None,
    retries: int,
    timeout: float,
    sleep: Callable[[float], None],
) -> None:
    """K1/K4: `/health` 200 + 4 readiness alanının (#53) varlığı + enum
    değeri. `github_auth`/`gemini` "missing" ise strict'te FAIL, değilse WARN
    (strict = `strict_override` verilmişse o, yoksa `mode == "hosted"`)."""
    url = f"{api}/health"
    max_attempts = 1 + max(retries, 0)
    attempt = 0
    resp = Response(status=0, headers={}, body="")
    while True:
        attempt += 1
        resp = _call(
            fetch, url, method="GET", headers={"Accept": "application/json"}, timeout=timeout
        )
        if resp.status == 200 or attempt >= max_attempts:
            break
        sleep(RETRY_DELAY_S)

    if resp.status != 200:
        label = resp.status if resp.status else "bağlantı yok"
        rep.fail(f"GET {url} -> {label} ({resp.body})")
        return

    try:
        data = json.loads(resp.body)
    except json.JSONDecodeError:
        rep.fail(f"GET {url} -> 200 ama gövde JSON değil: {resp.body[:200]!r}")
        return
    if not isinstance(data, dict):
        rep.fail(f"GET {url} -> 200 ama gövde JSON nesnesi değil ({type(data).__name__})")
        return

    required_fields = ("status", "mode", "github_auth", "gemini")
    missing = [f for f in required_fields if f not in data]
    if missing:
        for f in missing:
            rep.fail(f"readiness alanı eksik: {f} (#53)")
        return

    healthy = True
    if data["status"] != "ok":
        rep.fail(f"/health status='{data['status']}' != 'ok'")
        healthy = False
    if data["mode"] not in ("local", "hosted"):
        rep.fail(f"/health mode='{data['mode']}' beklenmeyen (local|hosted olmalı)")
        healthy = False

    strict = strict_override if strict_override is not None else data["mode"] == "hosted"
    for field_name in ("github_auth", "gemini"):
        value = data[field_name]
        if value == "configured":
            rep.ok(f"/health {field_name}='configured'")
        elif strict:
            rep.fail(
                f"/health {field_name}='{value}' (strict mod — canlıda 'configured' beklenir)"
            )
        else:
            rep.warn(f"/health {field_name}='{value}' (degrade — canlıda 'configured' beklenir)")

    if healthy:
        rep.ok(f"GET {url} -> 200, status=ok, mode={data['mode']}")


def check_cors(api: str, web_origin: str, rep: Report, fetch: FetchFn, *, timeout: float) -> None:
    """K3: preflight VE gerçek GET cevabında `Access-Control-Allow-Origin`
    canlı web origin'iyle TAM eşleşir (`*` ayrı FAIL — #45 "asla yıldız").
    Preflight 3xx ise (Fly `force_https` + urllib OPTIONS redirect izlemez)
    özel mesaj: https:// kullan."""
    url = f"{api}/health"

    pre = _call(
        fetch,
        url,
        method="OPTIONS",
        headers={"Origin": web_origin, "Access-Control-Request-Method": "GET"},
        timeout=timeout,
    )
    if pre.status in _REDIRECT_STATUSES:
        rep.fail(
            f"CORS preflight OPTIONS {url} -> {pre.status} redirect — https:// ver "
            "(Fly force_https; urllib OPTIONS'ta redirect izlemez)"
        )
    elif pre.status not in (200, 204):
        rep.fail(f"CORS preflight OPTIONS {url} -> {pre.status} (200/204 bekleniyor)")
    else:
        acao = pre.header("access-control-allow-origin")
        if acao == "*":
            rep.fail("CORS preflight ACAO='*' kabul edilemez (#45 — asla yıldız)")
        elif acao != web_origin:
            rep.fail(f"CORS preflight ACAO='{acao}' != '{web_origin}'")
        else:
            rep.ok(f"CORS preflight OPTIONS {url} -> {pre.status}, ACAO='{acao}'")

    got = _call(fetch, url, method="GET", headers={"Origin": web_origin}, timeout=timeout)
    acao_get = got.header("access-control-allow-origin")
    if acao_get == "*":
        rep.fail("CORS GET ACAO='*' kabul edilemez (#45 — asla yıldız)")
    elif acao_get != web_origin:
        rep.fail(f"CORS GET {url} -> ACAO='{acao_get}' != '{web_origin}'")
    else:
        rep.ok(f"CORS GET {url} -> ACAO='{acao_get}'")


def _check_spa_response(resp: Response, url: str, pass_label: str, rep: Report) -> None:
    if resp.status in _REDIRECT_STATUSES:
        location = resp.header("location") or "?"
        rep.fail(
            f"SPA {pass_label} GET {url} -> {resp.status} (Location: {location}); "
            "deep-link doğrudan servis edilmiyor - SPA rewrite kuralı eksik"
        )
        return
    if resp.status != 200:
        label = resp.status if resp.status else "bağlantı yok"
        rep.fail(f"SPA {pass_label} GET {url} -> {label}")
        return
    if HTML_MARKER not in resp.body:
        rep.fail(f"SPA {pass_label} GET {url} -> 200 ama index.html değil (marker yok)")
        return
    ctype = (resp.header("content-type") or "").lower()
    if "html" not in ctype:
        rep.warn(f"SPA {pass_label} GET {url} -> content-type '{ctype}' html değil")
    rep.ok(f"SPA {pass_label} GET {url} -> 200 + marker")


def check_spa_routes(web: str, rep: Report, fetch: FetchFn, *, timeout: float) -> None:
    """K2: 6 route × 2 geçiş (doğrudan + cache-buster'lı "refresh"). İkisi de
    200 + `HTML_MARKER` olmalı — yalnız ilk geçiş test edilirse CDN/edge
    cache'inden gelen yanıt "soğuk yol 404" vakasını gizler (test #14)."""
    for route in ROUTES:
        url = f"{web}{route}"

        direct = _call(
            fetch,
            url,
            method="GET",
            headers={"Accept": "text/html"},
            timeout=timeout,
            allow_redirects=False,
        )
        _check_spa_response(direct, url, "doğrudan", rep)

        refresh_url = f"{url}?_smoke={int(time.time())}"
        refreshed = _call(
            fetch,
            refresh_url,
            method="GET",
            headers={"Accept": "text/html", "Cache-Control": "no-cache"},
            timeout=timeout,
            allow_redirects=False,
        )
        _check_spa_response(refreshed, refresh_url, "refresh", rep)


# E8 fail-open düzeltmesi: eski kod yalnız tam "1" değerini strict sayıyordu
# (`value.strip() == "1"`) — yani "true"/"yes"/"on" yazan operatör, strict'i
# AÇMAK isterken sessizce KAPATIYORDU (== "1" False döner). Yeni kural
# fail-safe: yalnız AÇIKÇA kapatan değerler strict'i kapatır; geri kalan her
# şey (tanınan "aç" değerleri + tanınmayan/typo değerler) strict'i açık
# bırakır. Tanımsız/boş None döner — mode-bazlı varsayım (docstring) DEĞİŞMEZ.
_STRICT_OFF_VALUES = frozenset({"0", "false", "no", "off"})


def _parse_strict(value: str | None) -> bool | None:
    if value is None or value.strip() == "":
        return None
    return value.strip().lower() not in _STRICT_OFF_VALUES


def _parse_float(value: str | None, default: float) -> float:
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_int(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    fetch: FetchFn = http_fetch,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Tüm karar mantığı burada koşar. `argv` şu an kullanılmıyor (env-only
    sözleşme) — imzada tutulur ki ileride bayrak eklemek çağıranları kırmasın."""
    del argv
    env = os.environ if env is None else env

    api_raw = (env.get("SMOKE_API_URL") or "").strip()
    web_raw = (env.get("SMOKE_WEB_URL") or "").strip()

    if not api_raw:
        print(
            "HATA: SMOKE_API_URL boş.\n"
            "  Zorunlu: SMOKE_API_URL (backend base URL)\n"
            "  Opsiyonel: SMOKE_WEB_URL (frontend base URL — yoksa CORS+SPA atlanır)\n"
            "  Örnek: SMOKE_API_URL=https://<app>.fly.dev "
            "SMOKE_WEB_URL=https://<app>.vercel.app make smoke",
            file=sys.stderr,
        )
        return 1

    timeout = _parse_float(env.get("SMOKE_TIMEOUT_S"), DEFAULT_TIMEOUT_S)
    retries = _parse_int(env.get("SMOKE_RETRIES"), DEFAULT_RETRIES)
    strict_override = _parse_strict(env.get("SMOKE_STRICT"))

    rep = Report()
    api = normalize_base(api_raw)

    api_scheme_ok = check_http_scheme(api_raw, "SMOKE_API_URL", rep)
    if api_scheme_ok:
        check_health(
            api,
            rep,
            fetch,
            strict_override=strict_override,
            retries=retries,
            timeout=timeout,
            sleep=sleep,
        )

    if web_raw:
        web = normalize_base(web_raw)
        web_scheme_ok = check_http_scheme(web_raw, "SMOKE_WEB_URL", rep)
        if api_scheme_ok and web_scheme_ok:
            check_cors(api, origin_of(web_raw), rep, fetch, timeout=timeout)
        if web_scheme_ok:
            check_spa_routes(web, rep, fetch, timeout=timeout)
    else:
        rep.warn(
            "SMOKE_WEB_URL verilmedi — CORS + SPA route kontrolleri ATLANDI (kısmi smoke)"
        )

    for line in rep.lines:
        print(line)

    if rep.failures:
        print(f"SMOKE KIRMIZI — {len(rep.failures)} hata, {len(rep.warnings)} uyarı")
        return 1

    suffix = f" ({len(rep.warnings)} uyarı)" if rep.warnings else ""
    print(f"SMOKE YEŞİL{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
