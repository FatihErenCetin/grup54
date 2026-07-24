"""Radar canli kablolama (#151) testleri.

Settings'e gore gercek/fake adapter secimini ve esik gecisini dogrular.
Gercek GitHubAdapter/GeminiJudgeAdapter construction'i network cagrisi
yapmaz (lazy) - sahte config degerleriyle guvenle test edilebilir.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from ensemble.app import _build_radar_service, create_app
from ensemble.config import Settings
from ensemble.engine.embeddings import CachedEmbeddings, HashEmbeddings
from ensemble.integrations.gemini.embeddings import GeminiEmbeddingsAdapter
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.gemini.query_judge import FakeQueryJudgeAdapter
from ensemble.integrations.gemini.scope_judge import FakeScopeJudgeAdapter
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.integrations.ollama.adapter import OllamaAdapter
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
