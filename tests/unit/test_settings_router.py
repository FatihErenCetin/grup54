"""`/settings/*` (T-307 FAZ 2) testleri — görev brifinginin BEŞ güvenlik
kuralının HER BİRİ için mutasyon-kanıtlı bir kilit:

  KURAL 1 — hosted'da 404 (`test_hosted_modda_*`)
  KURAL 2 — GET anahtarı ASLA tam döndürmez (`test_mask_key_*`, `test_get_*_maskeli`)
  KURAL 3 — `~/.ensemble/ayarlar.json`, disk üstünde doğrulanır (0600 dahil)
  KURAL 4 — `/settings/test` GERÇEK ağ çağrısı yapar, sonuç dürüst
  KURAL 5 — kaydetmek ÇALIŞAN SÜRECE devreder (`test_put_*_rebuild_*`)

Mutasyon kanıtları (PR gövdesinde raporlanır): her `MUTASYON KİLİDİ` yorumu
taşıyan test, ilgili korumayı geçici olarak kaldırıp KIRMIZI görüp geri
almakla doğrulandı.
"""

from __future__ import annotations

import stat

import httpx
import pytest
from fastapi.testclient import TestClient

import ensemble.api.routers.settings as settings_module
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.store.engine import get_engine
from ensemble.store.models import Base
from ensemble.store.provider_settings import read_provider_settings, settings_path


def _make_app(tmp_path, monkeypatch, *, mode: str = "local", **overrides):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    db_path = tmp_path / "e.db"
    settings = Settings(
        _env_file=None, ENSEMBLE_MODE=mode, DATABASE_URL=f"sqlite:///{db_path}", **overrides
    )
    app = create_app(settings)
    Base.metadata.create_all(get_engine(settings))
    return app, home


# ---------------------------------------------------------------------------
# KURAL 1 — yalnız local mod
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("get", "/settings/saglayici", None),
        ("put", "/settings/saglayici", {"saglayici": "gemini"}),
        ("post", "/settings/test", {"saglayici": "gemini"}),
        ("get", "/settings/mcp", None),
    ],
)
def test_hosted_modda_DORT_UCUN_DE_404_dondugu(tmp_path, monkeypatch, method, path, json_body):
    """MUTASYON KİLİDİ: `_require_local_mode`'daki `!=` kontrolünü kaldır
    (ya da `raise` satırını sil) → bu dört test KIRMIZI olur (hosted'da
    200/başka bir kod dönmeye başlar) — görev brifinginin "kapıyı kaldır →
    hosted'da uç erişilebilir → kırmızı" mutasyonunun ta kendisi."""
    app, _ = _make_app(tmp_path, monkeypatch, mode="hosted")
    with TestClient(app) as client:
        resp = getattr(client, method)(path, json=json_body) if json_body is not None else getattr(
            client, method
        )(path)
    assert resp.status_code == 404


def test_local_modda_saglayici_ucu_erisilebilir(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        resp = client.get("/settings/saglayici")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# KURAL 2 — maskeleme
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("a", "…"),
        ("abcd", "…"),
        ("abcde", "ab…de"),
        ("SAHTE-gemini-fixture-1234", "SAHT…1234"),
    ],
)
def test_mask_key_hicbir_zaman_TAM_anahtari_dondurmez(value, expected):
    assert settings_module._mask_key(value) == expected
    if value:
        # Ek güvence: maskelenmiş çıktı asla GİRDİYLE AYNI olmamalı (yoksa
        # maskeleme fiilen devre dışı demektir).
        assert settings_module._mask_key(value) != value


def test_get_anahtar_tanimliyken_maskeli_doner(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local", GEMINI_API_KEY="SAHTE-gemini-fixture-1234")
    with TestClient(app) as client:
        body = client.get("/settings/saglayici").json()
    assert body["anahtarlar"]["gemini"] == "SAHT…1234"
    assert "SAHTE-gemini-fixture-1234" not in str(body)


def test_get_anahtar_tanimsizken_null_doner(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        body = client.get("/settings/saglayici").json()
    assert body["anahtarlar"]["gemini"] is None
    assert body["anahtarlar"]["groq"] is None


# ---------------------------------------------------------------------------
# KURAL 3 — dosya konumu + izin
# ---------------------------------------------------------------------------


def test_put_diske_yazar_repoya_DEGIL(tmp_path, monkeypatch):
    app, home = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        resp = client.put(
            "/settings/saglayici", json={"saglayici": "gemini", "anahtar": "gizli-anahtar-123"}
        )
    assert resp.status_code == 200
    path = settings_path(home)
    assert path.is_file()
    assert read_provider_settings(home)["gemini_api_key"] == "gizli-anahtar-123"


@pytest.mark.skipif(
    __import__("sys").platform == "win32", reason="POSIX izin biti — Windows'ta anlamsız"
)
def test_put_sonrasi_dosya_izni_0600(tmp_path, monkeypatch):
    """MUTASYON KİLİDİ: `write_provider_settings`'teki `os.chmod` satırlarını
    kaldır → bu test kırmızı olur (dosya varsayılan umask ile daha geniş
    izinle kalır, ör. 0644)."""
    app, home = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        client.put("/settings/saglayici", json={"saglayici": "gemini", "anahtar": "k"})
    mode = stat.S_IMODE(settings_path(home).stat().st_mode)
    assert mode == 0o600


# ---------------------------------------------------------------------------
# PUT davranışı — sağlayıcı seçimi semantiği
# ---------------------------------------------------------------------------


def test_put_gemini_aktif_saglayiciyi_degistirir(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local", LLM_PROVIDER="ollama")
    with TestClient(app) as client:
        resp = client.put("/settings/saglayici", json={"saglayici": "gemini", "anahtar": "k"})
    assert resp.json()["saglayici"] == "gemini"


def test_put_groq_aktif_saglayiciyi_DEGISTIRMEZ(tmp_path, monkeypatch):
    """Groq yalnız bir YEDEK anahtar slotu — LLM_PROVIDER hiçbir zaman
    "groq" olamaz (bkz. app.py::_build_judge_port, Groq yalnız Gemini
    birincilken devreye giren bir FallbackJudge)."""
    app, _ = _make_app(tmp_path, monkeypatch, mode="local", LLM_PROVIDER="gemini")
    with TestClient(app) as client:
        resp = client.put("/settings/saglayici", json={"saglayici": "groq", "anahtar": "gk"})
    assert resp.json()["saglayici"] == "gemini"
    assert resp.json()["anahtarlar"]["groq"] is not None


def test_put_ollama_gecersiz_url_422(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        resp = client.put(
            "/settings/saglayici",
            json={"saglayici": "ollama", "ollama_url": "https://uzak-sunucu.example.com"},
        )
    assert resp.status_code == 422


def test_put_ollama_gecerli_loopback_url_kabul_edilir(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        resp = client.put(
            "/settings/saglayici",
            json={"saglayici": "ollama", "ollama_url": "http://127.0.0.1:12345"},
        )
    assert resp.status_code == 200
    assert resp.json()["ollama_url"] == "http://127.0.0.1:12345"


def test_put_anahtar_bos_string_mevcut_degeri_SILMEZ(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        client.put("/settings/saglayici", json={"saglayici": "gemini", "anahtar": "ilk-anahtar"})
        resp = client.put("/settings/saglayici", json={"saglayici": "gemini"})
    assert resp.json()["anahtarlar"]["gemini"] == settings_module._mask_key("ilk-anahtar")


# ---------------------------------------------------------------------------
# KURAL 5 — kaydetmek ÇALIŞAN SÜRECE devreder (rebuild)
# ---------------------------------------------------------------------------


def test_put_sonrasi_judge_port_GERCEKTEN_degisir(tmp_path, monkeypatch):
    """MUTASYON KİLİDİ: `update_provider_settings`'teki
    `rebuild_llm_services(request.app)` çağrısını kaldır → bu test kırmızı
    olur (`judge_port` PUT'tan SONRA da `FakeJudgeAdapter` olarak KALIR,
    çünkü `GeminiJudgeAdapter` hâlâ kurulmadı — anahtar dosyaya yazılmış
    olsa bile çalışan süreç eskisini kullanmaya devam eder)."""
    from ensemble.integrations.gemini.query_judge import GeminiQueryJudgeAdapter
    from ensemble.integrations.gemini.scope_judge import GeminiScopeJudgeAdapter

    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        # `app.state.radar_service` yalnız lifespan (yukarıdaki `with` bloğu)
        # BAŞLADIKTAN SONRA var olur — bu yüzden ilk kontrol de bu blok
        # İÇİNDE yapılır.
        assert isinstance(app.state.radar_service.judge_port, FakeJudgeAdapter)
        resp = client.put(
            "/settings/saglayici", json={"saglayici": "gemini", "anahtar": "SAHTE-anahtar-degeri"}
        )
    assert resp.status_code == 200
    assert isinstance(app.state.radar_service.judge_port, GeminiJudgeAdapter)
    assert isinstance(app.state.scope_service.judge_port, GeminiScopeJudgeAdapter)
    assert isinstance(app.state.query_service.judge_port, GeminiQueryJudgeAdapter)


def test_put_sonrasi_query_ve_scope_embeddings_de_GERCEK_gemini_olur(tmp_path, monkeypatch):
    from ensemble.engine.embeddings import CachedEmbeddings

    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        client.put("/settings/saglayici", json={"saglayici": "gemini", "anahtar": "SAHTE-anahtar-2"})
    assert isinstance(app.state.scope_service.embeddings_port, CachedEmbeddings)
    assert isinstance(app.state.query_service.embeddings_port, CachedEmbeddings)
    assert app.state.query_service.embeddings_port is app.state.radar_service.embeddings_port


def test_put_sonrasi_get_de_YENI_degeri_yansitir(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local", LLM_PROVIDER="ollama")
    with TestClient(app) as client:
        client.put("/settings/saglayici", json={"saglayici": "gemini", "anahtar": "k"})
        resp = client.get("/settings/saglayici")
    assert resp.json()["saglayici"] == "gemini"


def test_kaydedilmis_ayar_yeniden_baslatmada_da_devreye_girer(tmp_path, monkeypatch):
    """Süreç yeniden başlasa (`create_app` tekrar çağrılsa) bile
    `~/.ensemble/ayarlar.json`'daki kayıt `apply_provider_overlay` ile
    açılışta uygulanır — bir konteyner/paket yeniden yaratılsa da (kalıcı
    volume ile) kullanıcının girdiği anahtar KAYBOLMAZ."""
    app1, home = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app1) as client:
        client.put("/settings/saglayici", json={"saglayici": "gemini", "anahtar": "kalici-anahtar"})

    settings2 = Settings(
        _env_file=None,
        ENSEMBLE_MODE="local",
        DATABASE_URL=app1.state.base_settings.DATABASE_URL,
    )
    app2 = create_app(settings2)
    with TestClient(app2):
        assert isinstance(app2.state.radar_service.judge_port, GeminiJudgeAdapter)
        assert app2.state.settings.GEMINI_API_KEY == "kalici-anahtar"


# ---------------------------------------------------------------------------
# KURAL 4 — /settings/test GERÇEK ağ çağrısı yapar, "anahtar dolu = OK" YASAK
# ---------------------------------------------------------------------------


class _FakeApiError(Exception):
    def __init__(self, code: int):
        self.code = code
        super().__init__(f"api error {code}")


class _FakeGenaiModels:
    def __init__(self, exc: Exception | None = None):
        self._exc = exc

    def get(self, model):
        if self._exc is not None:
            raise self._exc
        return object()


class _FakeGenaiClient:
    def __init__(self, models):
        self.models = models


def _patch_genai(monkeypatch, exc: Exception | None = None):
    monkeypatch.setattr(settings_module.genai_errors, "APIError", _FakeApiError, raising=False)
    monkeypatch.setattr(
        settings_module.genai, "Client", lambda **kwargs: _FakeGenaiClient(_FakeGenaiModels(exc))
    )


def test_gemini_anahtar_tanimsizsa_agsiz_false_doner(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        resp = client.post("/settings/test", json={"saglayici": "gemini"})
    assert resp.json() == {"calisiyor": False, "mesaj": "Gemini anahtarı tanımlı değil."}


def test_gemini_gecerli_anahtar_calisiyor_true(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local", GEMINI_API_KEY="k")
    _patch_genai(monkeypatch, exc=None)
    with TestClient(app) as client:
        resp = client.post("/settings/test", json={"saglayici": "gemini"})
    assert resp.json()["calisiyor"] is True


def test_gemini_401_GECERSIZ_anahtarda_calisiyor_FALSE(tmp_path, monkeypatch):
    """MUTASYON KİLİDİ: `_test_gemini`'yi "anahtar dolu = OK" olacak şekilde
    (`return ProviderTestResponse(calisiyor=bool(settings.GEMINI_API_KEY), ...)`)
    değiştir → bu test KIRMIZI olur (401 dönen GERÇEK bir hata artık
    `calisiyor=True` olarak raporlanır — görev brifinginin "anahtar dolu =
    çalışıyor" fail-open'ının BİREBİR kendisi)."""
    app, _ = _make_app(tmp_path, monkeypatch, mode="local", GEMINI_API_KEY="gecersiz-ama-dolu")
    _patch_genai(monkeypatch, exc=_FakeApiError(401))
    with TestClient(app) as client:
        resp = client.post("/settings/test", json={"saglayici": "gemini"})
    body = resp.json()
    assert body["calisiyor"] is False
    assert "401" in body["mesaj"]


def test_gemini_429_kota_mesaji_ayirt_edilir(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local", GEMINI_API_KEY="k")
    _patch_genai(monkeypatch, exc=_FakeApiError(429))
    with TestClient(app) as client:
        resp = client.post("/settings/test", json={"saglayici": "gemini"})
    body = resp.json()
    assert body["calisiyor"] is False
    assert "kota" in body["mesaj"].lower() or "429" in body["mesaj"]


def test_gemini_ag_hatasi_ayirt_edilir(tmp_path, monkeypatch):
    # `genai.Client(...)`'in KENDİSİ (kurucu) değil, yalnız `.models.get(...)`
    # çağrısı hata fırlatmalı — aksi halde `lifespan`'in KENDİ (eager)
    # `GeminiQueryJudgeAdapter`/`GeminiScopeJudgeAdapter` kurulumu da bu sahte
    # hatayı yakalar ve uygulama HİÇ AÇILMAZ (bkz. `_patch_genai` — Client
    # inşası her zaman BAŞARILI, yalnız `models.get` enjekte edilen `exc`'i
    # fırlatır).
    app, _ = _make_app(tmp_path, monkeypatch, mode="local", GEMINI_API_KEY="k")
    _patch_genai(monkeypatch, exc=ConnectionError("bağlantı koptu"))
    with TestClient(app) as client:
        resp = client.post("/settings/test", json={"saglayici": "gemini"})
    body = resp.json()
    assert body["calisiyor"] is False
    assert "ağ" in body["mesaj"].lower()


class _FakeHttpxResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400


class _FakeHttpxClient:
    def __init__(self, response=None, raise_exc=None, **kwargs):
        self._response = response
        self._raise_exc = raise_exc

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, path):
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response


def test_groq_anahtar_tanimsizsa_agsiz_false_doner(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        resp = client.post("/settings/test", json={"saglayici": "groq"})
    assert resp.json() == {"calisiyor": False, "mesaj": "Groq anahtarı tanımlı değil."}


def test_groq_gecerli_calisiyor_true(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local", GROQ_API_KEY="k")
    monkeypatch.setattr(
        settings_module.httpx,
        "Client",
        lambda **kwargs: _FakeHttpxClient(response=_FakeHttpxResponse(200)),
    )
    with TestClient(app) as client:
        resp = client.post("/settings/test", json={"saglayici": "groq"})
    assert resp.json()["calisiyor"] is True


def test_groq_401_calisiyor_false(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local", GROQ_API_KEY="gecersiz-ama-dolu")
    monkeypatch.setattr(
        settings_module.httpx,
        "Client",
        lambda **kwargs: _FakeHttpxClient(response=_FakeHttpxResponse(401)),
    )
    with TestClient(app) as client:
        resp = client.post("/settings/test", json={"saglayici": "groq"})
    body = resp.json()
    assert body["calisiyor"] is False
    assert "401" in body["mesaj"]


def test_ollama_ag_hatasinda_calisiyor_false_ve_sebep_soylenir(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    monkeypatch.setattr(
        settings_module.httpx,
        "Client",
        lambda **kwargs: _FakeHttpxClient(raise_exc=httpx.ConnectError("bağlantı reddedildi")),
    )
    with TestClient(app) as client:
        resp = client.post("/settings/test", json={"saglayici": "ollama"})
    body = resp.json()
    assert body["calisiyor"] is False
    assert "ağ" in body["mesaj"].lower()


def test_ollama_gecerli_calisiyor_true(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    monkeypatch.setattr(
        settings_module.httpx,
        "Client",
        lambda **kwargs: _FakeHttpxClient(response=_FakeHttpxResponse(200)),
    )
    with TestClient(app) as client:
        resp = client.post("/settings/test", json={"saglayici": "ollama"})
    assert resp.json()["calisiyor"] is True


# ---------------------------------------------------------------------------
# FAZ 4 — GET /settings/mcp
# ---------------------------------------------------------------------------


def test_mcp_config_mutlak_yol_ve_gecerli_json_doner(tmp_path, monkeypatch):
    import json as json_module

    app, _ = _make_app(tmp_path, monkeypatch, mode="local")
    with TestClient(app) as client:
        body = client.get("/settings/mcp").json()

    assert body["yol"].startswith("/"), "yol MUTLAK olmalı"
    assert body["yol"].endswith(".mcp.json")
    config = json_module.loads(body["config_json"])
    assert "ensemble" in config["mcpServers"]
    args = config["mcpServers"]["ensemble"]["args"]
    assert "ensemble_mcp.server" in " ".join(args)
    # Sahte bir "bağlandı" durumu YOK — yalnız {config_json, yol} sözleşmesi.
    assert set(body.keys()) == {"config_json", "yol"}
