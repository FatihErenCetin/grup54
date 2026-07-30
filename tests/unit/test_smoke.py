"""`scripts/smoke.py` testleri (#189) — urllib mock'lanmaz.

`FakeTransport` gerçek ağ sınırının yerini alır (`main(..., fetch=fake, ...)`);
assert'ler `main()`'in **gerçek karar yolundan** geçer (exit kodu + istek
günlüğü + mesaj alt-dizgisi). Her kural için yeşil/kırmızı çifti var — mantığı
silmek/gevşetmek en az bir testi kırar (bkz. issue #189 planındaki mutasyon
spot-check listesi).
"""

from __future__ import annotations

import http.server
import json
import threading
from urllib.error import URLError
from urllib.parse import urlsplit

import pytest

from scripts.smoke import (
    ROUTES,
    HTML_MARKER,
    Response,
    _parse_strict,
    http_fetch,
    main,
    normalize_base,
    origin_of,
)

API = "https://api.test"
WEB = "https://web.test"

GOOD_HEALTH = {
    "status": "ok",
    "mode": "hosted",
    "github_auth": "configured",
    "gemini": "configured",
}
GOOD_HEALTH_LOCAL = {
    "status": "ok",
    "mode": "local",
    "github_auth": "missing",
    "gemini": "missing",
}


def base_env(*, api: str = API, web: str | None = WEB, **extra: str) -> dict[str, str]:
    env = {"SMOKE_API_URL": api, "SMOKE_RETRIES": "0"}
    if web is not None:
        env["SMOKE_WEB_URL"] = web
    env.update(extra)
    return env


def html_ok(marker: str = HTML_MARKER) -> Response:
    body = f"<html><body><div {marker}></div></body></html>"
    return Response(200, {"content-type": "text/html"}, body)


def spa_script() -> dict[tuple[str, str], object]:
    return {("GET", route): html_ok() for route in ROUTES}


class FakeTransport:
    """Sahte transport (mock urllib DEĞİL — main()'e enjekte edilen fetch).

    `script`: (method, path) -> Response | list[Response] | Exception.
    `list` verilirse ardışık çağrılarda sırayla tüketilir (>1 elemanken pop,
    son eleman kalıcı olarak tekrar döner) — retry / iki-geçişli SPA testleri
    için (aynı path, farklı sıradaki cevap).
    """

    def __init__(
        self,
        script: dict[tuple[str, str], object] | None = None,
        *,
        default: Response | None = None,
    ) -> None:
        self.script = script or {}
        self.default = default if default is not None else Response(200, {}, "{}")
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self,
        url: str,
        *,
        method: str = "GET",
        headers=None,
        timeout: float = 15.0,
        allow_redirects: bool = True,
    ) -> Response:
        del allow_redirects  # FakeTransport script'i literal cevap döner; gerçek
        # redirect-izleme davranışı `test_http_fetch_allow_redirects_gercek_urllib`
        # (gerçek urllib) tarafından kilitlenir — burada yalnız imza uyumu için var.
        self.calls.append((method, url))
        path = urlsplit(url).path or "/"
        entry = self.script.get((method, path), self.default)
        if isinstance(entry, list):
            entry = entry.pop(0) if len(entry) > 1 else entry[0]
        if isinstance(entry, BaseException):
            raise entry
        return entry

    def call_paths(self) -> list[tuple[str, str]]:
        return [(m, urlsplit(u).path or "/") for m, u in self.calls]


def health_resp(body: dict, status: int = 200, headers: dict[str, str] | None = None) -> Response:
    return Response(status, headers or {"content-type": "application/json"}, json.dumps(body))


# ---------------------------------------------------------------------------
# K1/K4 — /health + readiness
# ---------------------------------------------------------------------------


def test_saglikli_deploy_yesil():
    script: dict[tuple[str, str], object] = {
        ("GET", "/health"): health_resp(
            GOOD_HEALTH,
            headers={"content-type": "application/json", "access-control-allow-origin": WEB},
        ),
        ("OPTIONS", "/health"): Response(200, {"access-control-allow-origin": WEB}, ""),
    }
    script.update(spa_script())
    fake = FakeTransport(script)
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 0
    assert not any(m == "OPTIONS" and p != "/health" for m, p in fake.call_paths())


def test_health_500_kirmizi():
    fake = FakeTransport({("GET", "/health"): Response(500, {}, "internal error")})
    rc = main(env=base_env(web=None), fetch=fake, sleep=lambda s: None)
    assert rc == 1


def test_health_json_degil_kirmizi():
    fake = FakeTransport({("GET", "/health"): Response(200, {}, "not-json-body")})
    rc = main(env=base_env(web=None), fetch=fake, sleep=lambda s: None)
    assert rc == 1


def test_readiness_alani_eksikse_kirmizi(capsys):
    body = {k: v for k, v in GOOD_HEALTH.items() if k != "gemini"}
    fake = FakeTransport({("GET", "/health"): health_resp(body)})
    rc = main(env=base_env(web=None), fetch=fake, sleep=lambda s: None)
    assert rc == 1
    assert "gemini" in capsys.readouterr().out


def test_hosted_modda_missing_readiness_kirmizi():
    body = {"status": "ok", "mode": "hosted", "github_auth": "missing", "gemini": "configured"}
    fake = FakeTransport({("GET", "/health"): health_resp(body)})
    rc = main(env=base_env(web=None), fetch=fake, sleep=lambda s: None)
    assert rc == 1


def test_local_modda_missing_readiness_yesil():
    body = {"status": "ok", "mode": "local", "github_auth": "missing", "gemini": "missing"}
    fake = FakeTransport({("GET", "/health"): health_resp(body)})
    rc = main(env=base_env(web=None), fetch=fake, sleep=lambda s: None)
    assert rc == 0


def test_smoke_strict_1_local_modda_da_kirmizi():
    body = {"status": "ok", "mode": "local", "github_auth": "missing", "gemini": "missing"}
    fake = FakeTransport({("GET", "/health"): health_resp(body)})
    rc = main(env=base_env(web=None, SMOKE_STRICT="1"), fetch=fake, sleep=lambda s: None)
    assert rc == 1


def test_smoke_strict_true_local_modda_da_kirmizi():
    """E8 regresyon kilidi (integration seviyesi): eski hata `SMOKE_STRICT=true`
    yazan operatörü sessizce non-strict'e düşürüyordu (`== "1"` tautolojisi
    False dönüyordu). Bu artık local modda da FAIL vermeli — tıpkı "1" gibi."""
    body = {"status": "ok", "mode": "local", "github_auth": "missing", "gemini": "missing"}
    fake = FakeTransport({("GET", "/health"): health_resp(body)})
    rc = main(env=base_env(web=None, SMOKE_STRICT="true"), fetch=fake, sleep=lambda s: None)
    assert rc == 1


def test_smoke_strict_0_hosted_modda_degrade_yesil():
    """`SMOKE_STRICT=0` — açıkça kapatan tek değerlerden biri — hosted modun
    otomatik-strict varsayımını bile geçersiz kılıp WARN'a düşürmeli
    (go-live checklist'inin "SMOKE_STRICT=0 ile boyanmamış" endişesinin
    tersi: burada BİLEREK 0 verilen durumu kilitliyoruz)."""
    body = {"status": "ok", "mode": "hosted", "github_auth": "missing", "gemini": "missing"}
    fake = FakeTransport({("GET", "/health"): health_resp(body)})
    rc = main(env=base_env(web=None, SMOKE_STRICT="0"), fetch=fake, sleep=lambda s: None)
    assert rc == 0


# ---------------------------------------------------------------------------
# _parse_strict — E8 fail-open düzeltmesi: her varyant için tautolojik
# OLMAYAN kilit (literal beklenen değer hardcode edilir, aynı fonksiyonun
# başka bir çağrısına karşı kıyaslanmaz).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["0", "false", "False", "FALSE", "no", "No", "NO", "off", "Off", "OFF"])
def test_parse_strict_acikca_kapatan_degerler_false(value):
    assert _parse_strict(value) is False


@pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "Yes", "YES", "on", "On", "ON"])
def test_parse_strict_acikca_acan_degerler_true(value):
    assert _parse_strict(value) is True


def test_parse_strict_tanimsiz_deger_none():
    assert _parse_strict(None) is None


def test_parse_strict_bos_deger_none():
    assert _parse_strict("") is None


def test_parse_strict_bosluk_deger_none():
    assert _parse_strict("   ") is None


@pytest.mark.parametrize("value", ["yolo", "evet", "TRUEISH", "2"])
def test_parse_strict_taninmayan_deger_fail_safe_true(value):
    """Tanınmayan/typo bir değer AÇIKÇA kapatan listede olmadığı sürece
    strict'i AÇIK bırakır (fail-safe) — eski davranış (yalnız tam "1" True,
    gerisi False) burada kesin olarak tersine döndü."""
    assert _parse_strict(value) is True


# ---------------------------------------------------------------------------
# K3 — CORS
# ---------------------------------------------------------------------------


def test_cors_acao_yoksa_kirmizi():
    script = {
        ("GET", "/health"): health_resp(GOOD_HEALTH),
        ("OPTIONS", "/health"): Response(200, {}, ""),
    }
    fake = FakeTransport(script)
    rc = main(env=base_env(web=WEB + "/"), fetch=fake, sleep=lambda s: None)
    assert rc == 1


def test_cors_acao_baska_origin_ise_kirmizi():
    other = "https://baska.example"
    script = {
        ("GET", "/health"): health_resp(
            GOOD_HEALTH, headers={"access-control-allow-origin": other}
        ),
        ("OPTIONS", "/health"): Response(200, {"access-control-allow-origin": other}, ""),
    }
    fake = FakeTransport(script)
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 1


def test_cors_acao_yildiz_kirmizi():
    script = {
        ("GET", "/health"): health_resp(GOOD_HEALTH, headers={"access-control-allow-origin": "*"}),
        ("OPTIONS", "/health"): Response(200, {"access-control-allow-origin": "*"}, ""),
    }
    fake = FakeTransport(script)
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 1


def test_cors_preflight_3xx_kirmizi(capsys):
    script = {
        ("GET", "/health"): health_resp(GOOD_HEALTH, headers={"access-control-allow-origin": WEB}),
        ("OPTIONS", "/health"): Response(301, {"location": API.replace("https", "http")}, ""),
    }
    fake = FakeTransport(script)
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 1
    out = capsys.readouterr().out
    assert "https" in out and "redirect" in out


# ---------------------------------------------------------------------------
# K2 — SPA route deep-link (doğrudan + refresh)
# ---------------------------------------------------------------------------


def _base_ok_script() -> dict[tuple[str, str], object]:
    script: dict[tuple[str, str], object] = {
        ("GET", "/health"): health_resp(GOOD_HEALTH, headers={"access-control-allow-origin": WEB}),
        ("OPTIONS", "/health"): Response(200, {"access-control-allow-origin": WEB}, ""),
    }
    script.update(spa_script())
    return script


def test_spa_tek_route_404_kirmizi(capsys):
    script = _base_ok_script()
    script[("GET", "/board")] = Response(404, {}, "not found")
    fake = FakeTransport(script)
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 1
    out = capsys.readouterr().out
    assert "/board" in out
    assert "OK   SPA doğrudan GET https://web.test/scope" in out


def test_spa_200_ama_index_degil_kirmizi(capsys):
    script = _base_ok_script()
    placeholder = Response(200, {"content-type": "text/html"}, "<html>placeholder</html>")
    script[("GET", "/ask")] = placeholder
    fake = FakeTransport(script)
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 1
    assert "index.html değil" in capsys.readouterr().out


def test_spa_refresh_geciside_kirilirsa_kirmizi():
    script = _base_ok_script()
    # /activity: ilk (doğrudan) geçiş 200+marker, ikinci (refresh) 404.
    script[("GET", "/activity")] = [html_ok(), Response(404, {}, "not found")]
    fake = FakeTransport(script)
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 1


def test_alti_route_iki_gecis_isteniyor():
    fake = FakeTransport(_base_ok_script())
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 0
    spa_calls = [(m, p) for m, p in fake.call_paths() if p in ROUTES]
    assert len(spa_calls) == len(ROUTES) * 2
    for route in ROUTES:
        assert spa_calls.count(("GET", route)) == 2


def test_spa_302_yonlendirme_fail_open_kirmizi(capsys):
    """DOĞRULANMIŞ BLOCKER (#189, Semih): eski davranış `http_fetch`'in
    `urlopen`'i çıplak kullanmasıydı — GET için 3xx VARSAYILAN OLARAK
    izlenir, redirect sonunda `/` (index.html) 200+marker döndüğü için
    hem doğrudan hem refresh geçişi "yeşil" görünüyordu; halbuki deep-link
    DOĞRUDAN servis edilmiyordu (SPA rewrite kuralı eksikti). Bu test 6
    route'un da `/` adresine 302 ile yönlendirildiği bir sahte transport
    kurar — `allow_redirects=False` çekirdeği çalışıyorsa exit 1 olmalı VE
    rapor redirect'i (Location dahil) açıkça anlatmalı."""
    script = _base_ok_script()
    for route in ROUTES:
        script[("GET", route)] = Response(302, {"location": f"{WEB}/"}, "")
    fake = FakeTransport(script)
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 1
    out = capsys.readouterr().out
    assert "302" in out
    assert "Location:" in out
    assert "deep-link doğrudan servis edilmiyor" in out
    # Redirect izlenip `/`'e "geldiği" için sahte-yeşil vermemeli: `/`
    # dışındaki route'lar için hiçbir OK satırı görünmemeli.
    for route in ROUTES:
        if route == "/":
            continue
        assert f"OK   SPA doğrudan GET {WEB}{route}" not in out
        assert f"OK   SPA refresh GET {WEB}{route}" not in out


def test_spa_302_ayni_host_rewrite_mesaji(capsys):
    """ISTENEN 2 - aynı-host dalı: Location HOST'suz (relative, örn. "/")
    ise mevcut "SPA rewrite kuralı eksik" teşhisi DEĞİŞMEMELİ (kanonik alan
    yönlendirmesi mesajı YANLIŞLIKLA burada tetiklenmemeli)."""
    script = _base_ok_script()
    script[("GET", "/board")] = Response(302, {"location": "/"}, "")
    fake = FakeTransport(script)
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 1
    out = capsys.readouterr().out
    assert "SPA rewrite kuralı eksik" in out
    assert "kanonik alan yönlendirmesi" not in out


def test_spa_302_farkli_host_kanonik_alan_mesaji(capsys):
    """ISTENEN 2 - farklı-host dalı: Location'ın HOST'u istenen host'tan
    farklıysa (örn. www->apex kanonik alan yönlendirmesi) kök neden "SPA
    rewrite kuralı eksik" DEĞİL — SMOKE_WEB_URL'in kanonik olmayan hostu
    olabilir; ayrı ve doğru bir mesaj basılmalı, eski rewrite mesajı
    BASILMAMALI."""
    script = _base_ok_script()
    script[("GET", "/board")] = Response(302, {"location": "https://baska-host.example/"}, "")
    fake = FakeTransport(script)
    rc = main(env=base_env(), fetch=fake, sleep=lambda s: None)
    assert rc == 1
    out = capsys.readouterr().out
    assert "kanonik alan yönlendirmesi" in out
    assert "SMOKE_WEB_URL'i canonical URL'e çevir" in out
    assert "SPA rewrite kuralı eksik" not in out


class _RedirectingSpaHandler(http.server.BaseHTTPRequestHandler):
    """Gerçek bir "bozuk deploy"u taklit eden minik HTTP sunucusu: `/`
    dışındaki HER yolu `/`'e 302 ile yönlendirir; `/` 200 + `HTML_MARKER`
    döner. `test_http_fetch_allow_redirects_gercek_urllib` bunun üzerinden
    `urllib`'in GERÇEK `HTTPRedirectHandler` zincirini koşar (sahte
    transport'un ölçemeyeceği kısım — urlopen'in varsayılan izleme
    davranışının kendisi)."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler sözleşmesi
        if self.path == "/":
            body = f'<html><body><div {HTML_MARKER}></div></body></html>'.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # pragma: no cover
        pass  # test çıktısını http.server access-log'uyla kirletme


def test_http_fetch_allow_redirects_gercek_urllib():
    """(a) testi (yukarısı) yalnız SAHTE transport'u ölçer — tek başına
    yetersizdir çünkü `FakeTransport` zaten `allow_redirects`'i yok sayıp
    script'teki literal cevabı döner. Bu test kritik boşluğu kapatır:
    GERÇEK `urllib` + gerçek bir 127.0.0.1 sunucusu üzerinden hem (1)
    `allow_redirects=False`'in gerçekten 302'yi İZLEMEDİĞİNİ hem de (2)
    varsayılanın (`allow_redirects=True`) gerçekten izleyip 200'e vardığını
    kilitler — ikisi de doğrulanmazsa fail-open regresyonu sessizce geri
    gelebilir."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _RedirectingSpaHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        deep_link = f"http://127.0.0.1:{port}/board"

        not_followed = http_fetch(deep_link, allow_redirects=False, timeout=2.0)
        assert not_followed.status == 302
        assert not_followed.header("location") == "/"

        followed = http_fetch(deep_link, allow_redirects=True, timeout=2.0)
        assert followed.status == 200
        assert HTML_MARKER in followed.body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def _make_cors_health_handler(allowed_origin: str) -> type:
    """`/health`'e GET+OPTIONS'ta sağlıklı + CORS-uyumlu (ACAO tam eşleşir)
    cevap veren gerçek bir handler sınıfı üretir — ISTENEN 1 uçtan-uca
    testlerinde "backend" rolünü oynar."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                body = json.dumps(GOOD_HEALTH).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", allowed_origin)
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def do_OPTIONS(self) -> None:
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # pragma: no cover
            pass  # test çıktısını http.server access-log'uyla kirletme

    return _Handler


class _AlwaysOkSpaHandler(http.server.BaseHTTPRequestHandler):
    """Sağlıklı deploy taklidi: HER GET yoluna (deep-link + refresh dahil)
    doğrudan 200 + `HTML_MARKER` döner — rewrite kuralı doğru kurulmuş
    senaryosu (ISTENEN 1 (b))."""

    def do_GET(self) -> None:
        body = f'<html><body><div {HTML_MARKER}></div></body></html>'.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # pragma: no cover
        pass  # test çıktısını http.server access-log'uyla kirletme


def _start_server(handler_class: type) -> tuple[http.server.HTTPServer, threading.Thread]:
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server: http.server.HTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2.0)


def test_e2e_bozuk_deploy_main_gercek_soketle_kirmizi():
    """ISTENEN 1(a) — UÇTAN UCA DİKİŞ KİLİDİ: `check_spa_routes` ile
    `http_fetch` arasındaki `allow_redirects=False` kablosunu, `main()`'i
    GERÇEK 127.0.0.1 URL'leriyle (SMOKE_API_URL + SMOKE_WEB_URL env) koşarak
    kilitler — FakeTransport'un `allow_redirects`'i yok saydığı boşluğu
    kapatır. /health + CORS sağlıklı, "/" 200+marker, DİĞER tüm route'lar
    "/"'e 302 — issue #189 kabul kriteri: main() 1 dönmeli."""
    web_server, web_thread = _start_server(_RedirectingSpaHandler)
    web_url = f"http://127.0.0.1:{web_server.server_port}"

    api_handler = _make_cors_health_handler(web_url)
    api_server, api_thread = _start_server(api_handler)
    api_url = f"http://127.0.0.1:{api_server.server_port}"

    try:
        env = {
            "SMOKE_API_URL": api_url,
            "SMOKE_WEB_URL": web_url,
            "SMOKE_RETRIES": "0",
            "SMOKE_TIMEOUT_S": "2",
        }
        rc = main(env=env)
        assert rc == 1
    finally:
        _stop_server(web_server, web_thread)
        _stop_server(api_server, api_thread)


def test_e2e_saglikli_deploy_main_gercek_soketle_yesil():
    """ISTENEN 1(b) — aynı gerçek-soket düzeneği, sağlıklı deploy: TÜM
    deep-link'ler doğrudan 200+marker döner (redirect yok). main() 0
    dönmeli (yanlış pozitif YOK) — (a) ile birlikte hem fail-open hem
    fail-closed yönünü kilitler."""
    web_server, web_thread = _start_server(_AlwaysOkSpaHandler)
    web_url = f"http://127.0.0.1:{web_server.server_port}"

    api_handler = _make_cors_health_handler(web_url)
    api_server, api_thread = _start_server(api_handler)
    api_url = f"http://127.0.0.1:{api_server.server_port}"

    try:
        env = {
            "SMOKE_API_URL": api_url,
            "SMOKE_WEB_URL": web_url,
            "SMOKE_RETRIES": "0",
            "SMOKE_TIMEOUT_S": "2",
        }
        rc = main(env=env)
        assert rc == 0
    finally:
        _stop_server(web_server, web_thread)
        _stop_server(api_server, api_thread)


def test_routes_sabit_liste_ile_esit():
    """B1 regresyon kilidi — tautolojik DEĞİL: `test_alti_route_iki_gecis_
    isteniyor` beklentilerini ROUTES'un KENDİSİNDEN türetir (`for route in
    ROUTES`), yani ROUTES burada sessizce kısalır/uzar/yeniden sıralanırsa o
    test yine kendine göre geçer (self-referans → yanlış güvence — bkz.
    scripts/smoke.py:65 civarı düzeltilen yorum). Bu test literal (hardcode)
    6 route'a karşı karşılaştırır; src/frontend/src/main.tsx <Routes> ile
    burası sessizce sapınca YALNIZ bu test kırılır."""
    assert ROUTES == ("/", "/board", "/scope", "/graph", "/activity", "/ask")


def test_web_url_yoksa_web_bloklari_atlanir():
    fake = FakeTransport({("GET", "/health"): health_resp(GOOD_HEALTH)})
    rc = main(env=base_env(web=None), fetch=fake, sleep=lambda s: None)
    assert rc == 0
    assert all(m != "OPTIONS" for m, _ in fake.calls)
    assert all(urlsplit(u).hostname == urlsplit(API).hostname for _, u in fake.calls)


# ---------------------------------------------------------------------------
# Kullanım hatası / bağlantı hatası / normalize / origin
# ---------------------------------------------------------------------------


def test_api_url_yoksa_exit_1_ve_mesaj(capsys):
    fake = FakeTransport({})
    rc = main(env={}, fetch=fake, sleep=lambda s: None)
    assert rc == 1
    assert "SMOKE_API_URL" in capsys.readouterr().err
    assert fake.calls == []


def test_baglanti_hatasi_kirmizi(capsys):
    fake = FakeTransport({("GET", "/health"): URLError("[Errno 61] Connection refused")})
    rc = main(env=base_env(api="https://dead.test", web=None), fetch=fake, sleep=lambda s: None)
    assert rc == 1
    out = capsys.readouterr().out
    assert "dead.test" in out
    assert "Traceback" not in out


def test_trailing_slash_normalize():
    fake = FakeTransport(_base_ok_script())
    rc = main(env=base_env(api=API + "/", web=WEB + "/"), fetch=fake, sleep=lambda s: None)
    assert rc == 0
    urls = [u for _, u in fake.calls]
    assert f"{API}/health" in urls
    assert not any("//health" in u for u in urls)
    assert any(u == f"{WEB}/board" for u in urls)
    assert not any("//board" in u for u in urls)


def test_origin_of_yol_ve_portu_dogru_ayirir():
    assert origin_of("https://app.vercel.app/board?x=1") == "https://app.vercel.app"
    assert origin_of("http://127.0.0.1:4173/x") == "http://127.0.0.1:4173"


def test_normalize_base_sondaki_slash_kirpilir():
    assert normalize_base("http://api.test/") == "http://api.test"
    assert normalize_base("http://api.test") == "http://api.test"


def test_http_semasi_canli_hostta_kirmizi_localhostta_yesil():
    local_fake = FakeTransport({("GET", "/health"): health_resp(GOOD_HEALTH_LOCAL)})
    rc_local = main(
        env=base_env(api="http://127.0.0.1:8000", web=None), fetch=local_fake, sleep=lambda s: None
    )
    assert rc_local == 0
    assert local_fake.calls  # health gercekten cagrildi

    live_fake = FakeTransport({("GET", "/health"): health_resp(GOOD_HEALTH)})
    rc_live = main(
        env=base_env(api="http://canli.example.com", web=None),
        fetch=live_fake,
        sleep=lambda s: None,
    )
    assert rc_live == 1
    assert live_fake.calls == []  # semaguard health'i hic cagirmadan durdurdu


def test_soguk_baslangic_retry_siniri_basarili():
    sequence = [Response(503, {}, "cold"), health_resp(GOOD_HEALTH)]
    fake = FakeTransport({("GET", "/health"): sequence})
    rc = main(env=base_env(web=None, SMOKE_RETRIES="2"), fetch=fake, sleep=lambda s: None)
    assert rc == 0
    assert len(fake.calls) == 2


def test_soguk_baslangic_retry_siniri_kalici_503():
    fake = FakeTransport({("GET", "/health"): Response(503, {}, "down")})
    rc = main(env=base_env(web=None, SMOKE_RETRIES="2"), fetch=fake, sleep=lambda s: None)
    assert rc == 1
    assert len(fake.calls) == 3  # 1 + SMOKE_RETRIES


# ---------------------------------------------------------------------------
# CP1252 regresyonu (Semih'in canli Windows bulgusu, 2026-07-27)
# ---------------------------------------------------------------------------


def _cp1252_strict_akis():
    """Windows varsayilan konsolunun taklidi: CP1252 + errors='strict'."""
    import io

    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", newline="")


def test_yaz_CP1252_strict_akista_PATLAMAZ():
    """MUTASYON KILIDI: `yaz()` duz `print`'e cevrilirse bu test kirilir.

    Gercek dusus: Windows'ta varsayilan stdout CP1252. Rapor satirindaki
    Turkce 'g-breve' basilirken `print` UnicodeEncodeError firlatiyor,
    script exit 1 ile oluyor ve SPA kontrollerine HIC ULASAMIYOR -- yani
    hedef sistem tamamen saglikliyken smoke KIRMIZI raporluyordu.
    """
    from scripts.smoke import yaz

    akis = _cp1252_strict_akis()
    yaz("SMOKE YEŞİL — 6 rota doğrulandı, çakışma yok", akis)  # ğ, ş, ı, ç

    akis.flush()
    cikti = akis.buffer.getvalue().decode("cp1252")
    assert "SMOKE" in cikti, "satir hic yazilmamis"
    assert "rota" in cikti, "ASCII kisim korunmali"


def test_duz_print_ayni_akista_GERCEKTEN_patliyor():
    """Yukaridaki testin anlamli oldugunun kaniti.

    `yaz()` olmadan ayni akis+ayni metin PATLIYOR. Bu olmadan ust test
    "belki cp1252 zaten Turkce karakteri kaldiriyordur" suphesine acik
    kalirdi -- kilidin gercekten bir sey tuttugunu burada gosteriyoruz.
    """
    akis = _cp1252_strict_akis()
    with pytest.raises(UnicodeEncodeError):
        print("SMOKE YEŞİL — çakışma yok", file=akis)


def test_utf8_ayarla_reconfigure_OLMAYAN_akista_patlamaz():
    """stdout her zaman TextIOWrapper degil (pipe, IDE konsolu, test sahtesi).
    Kodlama ayarlanamiyorsa sessizce geciyoruz -- `yaz()` ikinci savunma."""
    from scripts.smoke import utf8_ayarla

    class _Reconfigureu_Olmayan:
        encoding = "cp1252"

        def write(self, s):
            return len(s)

    utf8_ayarla(_Reconfigureu_Olmayan())  # raise ETMEMELI


def test_utf8_ayarla_reconfigure_HATA_verse_de_patlamaz():
    """Bazi akislar `reconfigure` tasir ama cagirinca hata verir (or. detached
    buffer). Kurulum adimi smoke'u dusurmemeli."""
    from scripts.smoke import utf8_ayarla

    class _Kizan:
        encoding = "cp1252"

        def reconfigure(self, **kwargs):
            raise ValueError("underlying buffer detached")

    utf8_ayarla(_Kizan())  # raise ETMEMELI
