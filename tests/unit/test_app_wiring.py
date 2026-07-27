"""Radar canli kablolama (#151) testleri.

Settings'e gore gercek/fake adapter secimini ve esik gecisini dogrular.
Gercek GitHubAdapter/GeminiJudgeAdapter construction'i network cagrisi
yapmaz (lazy) - sahte config degerleriyle guvenle test edilebilir.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from ensemble.app import (
    _build_radar_service,
    _gemini_single_flight_wait_s,
    _ollama_single_flight_wait_s,
    create_app,
    _groq_single_flight_wait_s,
    _build_judge_port,
)
from ensemble.config import Settings
from ensemble.engine.fallback import FallbackJudge
from ensemble.engine.cache import CachedConflictJudge, CachedQueryJudge, CachedScopeJudge
from ensemble.engine.embeddings import CachedEmbeddings, HashEmbeddings
from ensemble.integrations.gemini.client import RETRY_WAIT_CAP_S
from ensemble.integrations.gemini.embeddings import GeminiEmbeddingsAdapter
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.gemini.query_judge import FakeQueryJudgeAdapter, GeminiQueryJudgeAdapter
from ensemble.integrations.gemini.scope_judge import FakeScopeJudgeAdapter, GeminiScopeJudgeAdapter
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.integrations.ollama.adapter import OllamaAdapter
from ensemble.integrations.ollama.client import RETRY_WAIT_CAP_S as OLLAMA_RETRY_WAIT_CAP_S
from ensemble.integrations.query_source import HarnessEventQuerySource
from ensemble.store.vector_store import LocalVectorIndex

_ENV_KEYS = [
    "GEMINI_API_KEY",
    "LLM_PROVIDER",
    "GITHUB_APP_ID",
    "GITHUB_APP_PRIVATE_KEY_PATH",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_REPO_OWNER",
    "GITHUB_REPO_NAME",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # _env_file=None yalniz .env dosyasini kapatir, shell'deki gercek
    # export'lari DEGIL - gelistiricinin makinesinde bu degiskenler set'liyse
    # testler yanilir (Fatih'in PR #159 review'inda repro'ladigi kirmizi suite).
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _full_github(pem_path) -> dict:
    return {
        "GITHUB_APP_ID": "123",
        "GITHUB_APP_PRIVATE_KEY_PATH": str(pem_path),
        "GITHUB_APP_INSTALLATION_ID": "456",
        "GITHUB_REPO_OWNER": "FatihErenCetin",
        "GITHUB_REPO_NAME": "grup54",
    }


def test_tam_config_gercek_adapterlari_secer(tmp_path):
    pem = tmp_path / "app.pem"
    pem.write_text("fake-pem-icerigi")
    settings = _settings(GEMINI_API_KEY="fake-key", **_full_github(pem))
    service = _build_radar_service(settings)
    assert isinstance(service.github_port, GitHubAdapter)
    assert isinstance(service.judge_port, GeminiJudgeAdapter)


def test_github_config_eksikse_fakeye_duser_ve_loglar(caplog):
    settings = _settings(GEMINI_API_KEY="fake-key")
    with caplog.at_level(logging.WARNING, logger="ensemble.wiring"):
        service = _build_radar_service(settings)
    assert isinstance(service.github_port, FakeGitHubAdapter)
    assert "GitHub App yapılandırması eksik" in caplog.text


def test_pem_icerigi_ile_diskte_pem_olmadan_gercek_adapter_secilir():
    """#186: yalnız GITHUB_APP_PRIVATE_KEY (içerik) ile, diskte .pem olmadan bile
    hosted engine gerçek GitHubAdapter'ı kurar."""
    settings = _settings(
        GEMINI_API_KEY="fake-key",
        GITHUB_APP_ID="123",
        GITHUB_APP_PRIVATE_KEY="fake-pem-icerigi",
        GITHUB_APP_INSTALLATION_ID="456",
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
    )
    service = _build_radar_service(settings)
    assert isinstance(service.github_port, GitHubAdapter)


def test_pem_dosyasi_yoksa_fakeye_duser_ve_loglar(tmp_path, caplog):
    # Alanlarin hepsi dolu ama pem gercekte yok - token yenilenene kadar
    # (istek anina kadar) fark edilmezdi; acilis-anina cektik.
    missing_pem = tmp_path / "yok.pem"
    settings = _settings(GEMINI_API_KEY="fake-key", **_full_github(missing_pem))
    with caplog.at_level(logging.WARNING, logger="ensemble.wiring"):
        service = _build_radar_service(settings)
    assert isinstance(service.github_port, FakeGitHubAdapter)
    assert "bulunamadı" in caplog.text


def test_gemini_key_eksikse_fakeye_duser_ve_loglar(tmp_path, caplog):
    pem = tmp_path / "app.pem"
    pem.write_text("fake-pem-icerigi")
    settings = _settings(**_full_github(pem))
    with caplog.at_level(logging.WARNING, logger="ensemble.wiring"):
        service = _build_radar_service(settings)
    assert isinstance(service.judge_port, FakeJudgeAdapter)
    assert "GEMINI_API_KEY tanımlı değil" in caplog.text


def test_gemini_key_varsa_cached_gemini_embeddings_secilir(tmp_path):
    pem = tmp_path / "app.pem"
    pem.write_text("fake-pem-icerigi")
    service = _build_radar_service(_settings(GEMINI_API_KEY="fake-key", **_full_github(pem)))
    assert isinstance(service.embeddings_port, CachedEmbeddings)
    assert isinstance(service.embeddings_port.inner, GeminiEmbeddingsAdapter)


def test_gemini_key_eksikse_hash_embeddings_secilir():
    service = _build_radar_service(_settings())
    assert isinstance(service.embeddings_port, HashEmbeddings)


@pytest.mark.parametrize("mode", ["local", "hosted"])
def test_ollama_provider_mode_ve_gemini_keyinden_bagimsiz_secilir(mode):
    settings = _settings(
        ENSEMBLE_MODE=mode,
        LLM_PROVIDER="ollama",
        GEMINI_API_KEY="bulunsa-bile-kullanma",
    )

    service = _build_radar_service(settings)

    assert isinstance(service.judge_port, OllamaAdapter)
    assert isinstance(service.embeddings_port, CachedEmbeddings)
    assert isinstance(service.embeddings_port.inner, OllamaAdapter)


def test_esikler_ve_default_base_settingsten_akar():
    settings = _settings(
        RADAR_WINDOW_DAYS=7,
        RADAR_MIN_JACCARD=0.3,
        RADAR_MIN_SIMILARITY=0.6,
        GITHUB_DEFAULT_BRANCH="develop",
    )
    service = _build_radar_service(settings)
    assert service.window_days == 7
    assert service.min_jaccard == 0.3
    assert service.min_similarity == 0.6
    assert service.default_base == "develop"


def test_app_state_lifespan_ile_radar_service_kurulur():
    # dependency_overrides YOK - gercek lifespan'in app.state.radar_service'i
    # kurdugunu dogrular (deps.get_radar_service'in okudugu yer).
    app = create_app(_settings())
    with TestClient(app) as client:
        resp = client.get("/radar")
    assert resp.status_code == 200
    assert resp.json()["detections"] == []


def test_app_state_lifespan_ile_query_service_kurulur():
    app = create_app(_settings())

    with TestClient(app):
        service = app.state.query_service
        assert isinstance(service.source_port, HarnessEventQuerySource)
        assert service.source_port.session_factory is not None
        assert isinstance(service.vector_index, LocalVectorIndex)
        assert isinstance(service.judge_port, FakeQueryJudgeAdapter)


def test_query_service_local_vector_indexi_fabrika_uzerinden_kuruyor(monkeypatch):
    """#170: build_vector_index export'ta kalmaz, gercek QueryService akisi tuketir."""
    built_index = LocalVectorIndex()
    calls = []

    def fake_build_vector_index(settings, *, session_factory=None):
        calls.append((settings.ENSEMBLE_MODE, session_factory))
        return built_index

    monkeypatch.setattr("ensemble.app.build_vector_index", fake_build_vector_index)
    app = create_app(_settings())

    with TestClient(app):
        assert app.state.query_service.vector_index is built_index

    assert calls == [("local", None)]


def test_app_state_lifespan_ile_scope_service_kurulur():
    app = create_app(_settings())

    with TestClient(app):
        assert app.state.scope_service.harness_port is not None
        assert isinstance(app.state.scope_service.judge_port, FakeScopeJudgeAdapter)


# --- Hosted demo cached-verdict wiring (#63) — demo acik/kapali matrisi ---
# GEMINI_API_KEY iki senaryoda da AYNI (dolu) tutulur ki judge_port/embeddings_port
# karsilastirmasi yalniz DEMO_MODE'a bagli olsun (baska bir degisken karismasin).


def _demo_wiring_settings(tmp_path, *, demo_mode: bool):
    db_path = tmp_path / f"demo-wiring-{demo_mode}.db"
    return _settings(
        GEMINI_API_KEY="fake-key",
        DEMO_MODE=demo_mode,
        GITHUB_REPO_OWNER="FatihErenCetin" if demo_mode else None,
        GITHUB_REPO_NAME="grup54" if demo_mode else None,
        DEMO_CACHE_MAX_ENTRIES=42,
        DATABASE_URL=f"sqlite:///{db_path}",
    )


def test_demo_kapali_iken_judge_sarmalanmaz(tmp_path):
    app = create_app(_demo_wiring_settings(tmp_path, demo_mode=False))

    with TestClient(app):
        assert isinstance(app.state.radar_service.judge_port, GeminiJudgeAdapter)
        assert isinstance(app.state.query_service.judge_port, GeminiQueryJudgeAdapter)
        assert isinstance(app.state.scope_service.judge_port, GeminiScopeJudgeAdapter)

        embeddings = app.state.radar_service.embeddings_port
        assert isinstance(embeddings, CachedEmbeddings)
        assert embeddings.max_entries is None  # demo kapali - sinirsiz (mevcut davranis)


def test_demo_acikken_judge_ve_embeddings_sarmalanir(tmp_path):
    app = create_app(_demo_wiring_settings(tmp_path, demo_mode=True))

    with TestClient(app):
        radar_judge = app.state.radar_service.judge_port
        assert isinstance(radar_judge, CachedConflictJudge)
        assert isinstance(radar_judge.inner, GeminiJudgeAdapter)

        query_judge = app.state.query_service.judge_port
        assert isinstance(query_judge, CachedQueryJudge)
        assert isinstance(query_judge.inner, GeminiQueryJudgeAdapter)

        scope_judge = app.state.scope_service.judge_port
        assert isinstance(scope_judge, CachedScopeJudge)
        assert isinstance(scope_judge.inner, GeminiScopeJudgeAdapter)

        embeddings = app.state.radar_service.embeddings_port
        assert isinstance(embeddings, CachedEmbeddings)
        assert embeddings.max_entries == 42  # demo acikken DEMO_CACHE_MAX_ENTRIES uygulanir


# --- Tekil-ucus bekleme suresi Gemini'nin gercek en-kotu-durumundan turetilir
#     (#63 ISTENEN 2) ---


def test_gemini_single_flight_wait_s_formulu():
    """N*timeout + (N-1)*retry_bekleme_tavani. Varsayilan ayarlarla
    (GEMINI_TIMEOUT_S=10.0, GEMINI_MAX_RETRIES=3, RETRY_WAIT_CAP_S=8.0):
    3*10 + 2*8 = 46.0 - PR govdesindeki "~46 sn surebilir" iddiasiyla birebir
    (sabit 30 sn'nin NEDEN erken zaman asimina ugradigini kanitlar)."""
    settings = Settings(_env_file=None, GEMINI_TIMEOUT_S=10.0, GEMINI_MAX_RETRIES=3)

    assert _gemini_single_flight_wait_s(settings) == 3 * 10.0 + 2 * RETRY_WAIT_CAP_S
    assert _gemini_single_flight_wait_s(settings) == 46.0


def test_gemini_single_flight_wait_s_tek_denemede_bekleme_yok():
    # N=1 -> aralarinda bekleme olacak deneme cifti yok (N-1=0)
    settings = Settings(_env_file=None, GEMINI_TIMEOUT_S=5.0, GEMINI_MAX_RETRIES=1)

    assert _gemini_single_flight_wait_s(settings) == 5.0


def test_ollama_single_flight_wait_s_formulu():
    """#63 sertlestirme turu: `_build_embeddings_port` Ollama dalina daha
    once GEMINI'den turetilen degeri enjekte ediyordu ("Ollama/Fake
    provider'da hic kullanilmaz" yorumu YANLISTI). Varsayilan ayarlarla
    (OLLAMA_TIMEOUT_S=60.0, OLLAMA_MAX_RETRIES=2, RETRY_WAIT_CAP_S=2.0):
    2*60 + 1*2 = 122.0 - PR govdesindeki "Ollama en-kotu-durum ~122 sn"
    iddiasiyla birebir (enjekte edilen Gemini degerinin - 46 sn - NEDEN
    erken zaman asimina ugrattigini kanitlar)."""
    settings = Settings(_env_file=None, OLLAMA_TIMEOUT_S=60.0, OLLAMA_MAX_RETRIES=2)

    assert _ollama_single_flight_wait_s(settings) == 2 * 60.0 + 1 * OLLAMA_RETRY_WAIT_CAP_S
    assert _ollama_single_flight_wait_s(settings) == 122.0


def test_ollama_single_flight_wait_s_tek_denemede_bekleme_yok():
    settings = Settings(_env_file=None, OLLAMA_TIMEOUT_S=15.0, OLLAMA_MAX_RETRIES=1)

    assert _ollama_single_flight_wait_s(settings) == 15.0


def test_embeddings_ollama_dalinda_kendi_single_flight_degerini_kullanir():
    """#63 sertlestirme turu: `_build_embeddings_port`in Ollama dali artik
    GEMINI'den DEGIL, KENDI `_ollama_single_flight_wait_s` turetmesinden
    beslenir - iki deger farkli kalsin diye ayarlar BILEREK Gemini
    varsayilanindan (46.0) FARKLI secilir."""
    settings = _settings(
        ENSEMBLE_MODE="local",
        LLM_PROVIDER="ollama",
        OLLAMA_TIMEOUT_S=60.0,
        OLLAMA_MAX_RETRIES=2,
        GEMINI_TIMEOUT_S=10.0,
        GEMINI_MAX_RETRIES=3,
    )
    expected_ollama = _ollama_single_flight_wait_s(settings)
    expected_gemini = _gemini_single_flight_wait_s(settings)
    assert expected_ollama != expected_gemini  # iki formul birbirinden BAGIMSIZ

    service = _build_radar_service(settings)

    assert isinstance(service.embeddings_port, CachedEmbeddings)
    assert isinstance(service.embeddings_port.inner, OllamaAdapter)
    assert service.embeddings_port.cache.single_flight_wait_s == expected_ollama


def test_judge_ollama_dalinda_kendi_single_flight_degerini_kullanir(tmp_path):
    """T-63 son tur (MADDE 3): `_build_judge_port` LLM_PROVIDER'dan BAGIMSIZ
    olarak HER ZAMAN `_gemini_single_flight_wait_s` enjekte ediyordu - hemen
    bir alttaki `_build_embeddings_port`in Ollama dali icin daha once
    duzeltilen (`_ollama_single_flight_wait_s`) ayni hatanin duzeltilmemis
    ikizi (DEMO_MODE=true + LLM_PROVIDER=ollama'da judge cache'i gercek
    ~122sn yerine Gemini'nin ~46sn'sini bekliyordu). Ayarlar varsayilan
    kalir ki iki formul (46.0 vs 122.0) dogal olarak FARKLI olsun."""
    db_path = tmp_path / "demo-wiring-judge-ollama.db"
    settings = _settings(
        LLM_PROVIDER="ollama",
        DEMO_MODE=True,
        GEMINI_API_KEY="bulunsa-bile-kullanma",
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
        DEMO_CACHE_MAX_ENTRIES=42,
        DATABASE_URL=f"sqlite:///{db_path}",
    )
    expected_ollama = _ollama_single_flight_wait_s(settings)
    expected_gemini = _gemini_single_flight_wait_s(settings)
    assert expected_ollama != expected_gemini  # iki formul birbirinden BAGIMSIZ

    app = create_app(settings)

    with TestClient(app):
        radar_judge = app.state.radar_service.judge_port
        assert isinstance(radar_judge, CachedConflictJudge)
        assert isinstance(radar_judge.inner, OllamaAdapter)
        assert radar_judge.cache.single_flight_wait_s == expected_ollama


def test_demo_acikken_judge_kilit_bekleme_suresi_gemini_ayarlarindan_turer(tmp_path):
    """Sabit 30sn DEGIL - gercek wiring'de (app.py lifespan) judge/embeddings
    sarmalayicilarinin ALTINDAKI TtlLruCache, GEMINI_TIMEOUT_S/MAX_RETRIES'ten
    turetilen degeri kullanmali (#63 ISTENEN 2 - ISTENEN sadece formulu degil,
    wiring'i de kilitler)."""
    db_path = tmp_path / "demo-wiring-single-flight.db"
    settings = _settings(
        GEMINI_API_KEY="fake-key",
        DEMO_MODE=True,
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
        DEMO_CACHE_MAX_ENTRIES=42,
        DATABASE_URL=f"sqlite:///{db_path}",
        GEMINI_TIMEOUT_S=20.0,
        GEMINI_MAX_RETRIES=2,
    )
    expected = _gemini_single_flight_wait_s(settings)
    assert expected != 30.0  # varsayilan sabitten farkli oldugunu da dogrula

    app = create_app(settings)

    with TestClient(app):
        radar_judge = app.state.radar_service.judge_port
        assert isinstance(radar_judge, CachedConflictJudge)
        assert radar_judge.cache.single_flight_wait_s == expected

        query_judge = app.state.query_service.judge_port
        assert isinstance(query_judge, CachedQueryJudge)
        assert query_judge.cache.single_flight_wait_s == expected

        scope_judge = app.state.scope_service.judge_port
        assert isinstance(scope_judge, CachedScopeJudge)
        assert scope_judge.cache.single_flight_wait_s == expected

        embeddings = app.state.radar_service.embeddings_port
        assert isinstance(embeddings, CachedEmbeddings)
        assert embeddings.cache.single_flight_wait_s == expected


# ---------------------------------------------------------------------------
# #255 inceleme bulgulari — yedek saglayici sarmasinin iki yan etkisi
# ---------------------------------------------------------------------------


def test_ollama_birincilken_groq_yedegi_KURULMAZ(tmp_path):
    """Tam-yerel gizlilik modu buluta dusmemeli — README'nin acik vaadi.

    README §"Tam-yerel gizlilik modu (Ollama)": *"LLM_PROVIDER=ollama
    secildiginde hem embeddings hem judge yerel Ollama API'sini kullanir;
    Gemini anahtari tanimli olsa bile buluta geri dusmez."*

    MUTASYON KILIDI: app.py'deki kosulu DAHIL ETME listesinden
    (`isinstance(judge, GeminiJudgeAdapter)`) hariç tutma listesine
    (`not isinstance(judge, FakeJudgeAdapter)`) cevir -> bu test kirilir.
    Ilk yazimda tam olarak o hariç tutma listesi vardi ve Ollama dalini da
    yakaliyordu: yerel-kal modu secen kullanicinin `actor=` (GitHub kullanici
    adlari) ve `files=` (repo yollari) iceren prompt'u api.groq.com'a giderdi.
    """
    settings = _settings(
        LLM_PROVIDER="ollama",
        GROQ_API_KEY="yedek-olsa-bile-kullanma",
        GEMINI_API_KEY="bulunsa-bile-kullanma",
        DATABASE_URL=f"sqlite:///{tmp_path / 'ollama-yedeksiz.db'}",
    )

    judge = _build_judge_port(settings)

    assert isinstance(judge, OllamaAdapter)
    assert not isinstance(judge, FallbackJudge)


def test_fake_birincilken_groq_yedegi_kurulmaz(tmp_path):
    """FakeJudgeAdapter hic dusmez — yedek anlamsiz olurdu."""
    settings = _settings(
        GEMINI_API_KEY="",
        GROQ_API_KEY="q",
        DATABASE_URL=f"sqlite:///{tmp_path / 'fake-yedeksiz.db'}",
    )
    assert isinstance(_build_judge_port(settings), FakeJudgeAdapter)


def test_yedek_varken_tekil_ucus_butcesi_TOPLAMSAL(tmp_path):
    """Cache'in kilit beklemesi iki saglayicinin en-kotu suresini de kapsamali.

    `FallbackJudge.judge_conflict` once birincilin TUM retry'larini tuketir,
    sonra yedegin retry'larini tuketir — yani tek cagrinin en-kotu suresi
    toplamsaldir. Cache'e yalnizca birincilin butcesi verilirse, kilit tam da
    yedegin devreye girdigi anda (= kotanin bittigi an) zaman asimina ugrar ve
    bekleyen thread'ler KILITSIZ devam eder: her biri kendi saglayici cagrisini
    yapar, tekil-ucus katmani delinir.

    MUTASYON KILIDI: app.py'de `single_flight_budget += _groq_...` satirini sil
    -> butce 46.0'da kalir, bu test kirilir.
    """
    settings = _settings(
        GEMINI_API_KEY="g",
        GROQ_API_KEY="q",
        DEMO_MODE=True,
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
        DATABASE_URL=f"sqlite:///{tmp_path / 'yedek-butce.db'}",
    )
    beklenen = _gemini_single_flight_wait_s(settings) + _groq_single_flight_wait_s(settings)
    assert beklenen > _gemini_single_flight_wait_s(settings)  # toplam gercekten BUYUK

    judge = _build_judge_port(settings)

    assert isinstance(judge, CachedConflictJudge)
    assert isinstance(judge.inner, FallbackJudge)
    assert judge.cache.single_flight_wait_s == beklenen


def test_yedek_yokken_butce_degismez(tmp_path):
    """Groq anahtari yoksa butce eskisi gibi yalniz birincilden turer."""
    settings = _settings(
        GEMINI_API_KEY="g",
        GROQ_API_KEY="",
        DEMO_MODE=True,
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
        DATABASE_URL=f"sqlite:///{tmp_path / 'yedeksiz-butce.db'}",
    )
    judge = _build_judge_port(settings)
    assert judge.cache.single_flight_wait_s == _gemini_single_flight_wait_s(settings)
