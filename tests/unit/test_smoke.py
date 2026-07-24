"""`scripts/smoke.py` testleri (#189) — urllib mock'lanmaz.

`FakeTransport` gerçek ağ sınırının yerini alır (`main(..., fetch=fake, ...)`);
assert'ler `main()`'in **gerçek karar yolundan** geçer (exit kodu + istek
günlüğü + mesaj alt-dizgisi). Her kural için yeşil/kırmızı çifti var — mantığı
silmek/gevşetmek en az bir testi kırar (bkz. issue #189 planındaki mutasyon
spot-check listesi).
"""

from __future__ import annotations

import json
from urllib.error import URLError
from urllib.parse import urlsplit

from scripts.smoke import ROUTES, HTML_MARKER, Response, main, normalize_base, origin_of

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
        self, url: str, *, method: str = "GET", headers=None, timeout: float = 15.0
    ) -> Response:
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
