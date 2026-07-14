"""Radar canli kablolama (#151) testleri.

Settings'e gore gercek/fake adapter secimini ve esik gecisini dogrular.
Gercek GitHubAdapter/GeminiJudgeAdapter construction'i network cagrisi
yapmaz (lazy) - sahte config degerleriyle guvenle test edilebilir.
"""

import logging

from fastapi.testclient import TestClient

from ensemble.app import _build_radar_service, create_app
from ensemble.config import Settings
from ensemble.engine.embeddings import HashEmbeddings
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.fake import FakeGitHubAdapter

_FULL_GITHUB = {
    "GITHUB_APP_ID": "123",
    "GITHUB_APP_PRIVATE_KEY_PATH": "/tmp/does-not-need-to-exist.pem",
    "GITHUB_APP_INSTALLATION_ID": "456",
    "GITHUB_REPO_OWNER": "FatihErenCetin",
    "GITHUB_REPO_NAME": "grup54",
}


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_tam_config_gercek_adapterlari_secer():
    settings = _settings(GEMINI_API_KEY="fake-key", **_FULL_GITHUB)
    service = _build_radar_service(settings)
    assert isinstance(service.github_port, GitHubAdapter)
    assert isinstance(service.judge_port, GeminiJudgeAdapter)


def test_github_config_eksikse_fakeye_duser_ve_loglar(caplog):
    settings = _settings(GEMINI_API_KEY="fake-key")
    with caplog.at_level(logging.WARNING, logger="ensemble.wiring"):
        service = _build_radar_service(settings)
    assert isinstance(service.github_port, FakeGitHubAdapter)
    assert "GitHub App yapılandırması eksik" in caplog.text


def test_gemini_key_eksikse_fakeye_duser_ve_loglar(caplog):
    settings = _settings(**_FULL_GITHUB)
    with caplog.at_level(logging.WARNING, logger="ensemble.wiring"):
        service = _build_radar_service(settings)
    assert isinstance(service.judge_port, FakeJudgeAdapter)
    assert "GEMINI_API_KEY tanımlı değil" in caplog.text


def test_embeddings_15_kapaninca_kadar_hash_kalir():
    # #15 (gercek Gemini embeddings) acik oldugu surece HER modda HashEmbeddings.
    service = _build_radar_service(_settings(GEMINI_API_KEY="fake-key", **_FULL_GITHUB))
    assert isinstance(service.embeddings_port, HashEmbeddings)


def test_esikler_settingsten_akar():
    settings = _settings(
        RADAR_WINDOW_DAYS=7, RADAR_MIN_JACCARD=0.3, RADAR_MIN_SIMILARITY=0.6
    )
    service = _build_radar_service(settings)
    assert service.window_days == 7
    assert service.min_jaccard == 0.3
    assert service.min_similarity == 0.6


def test_app_state_lifespan_ile_radar_service_kurulur():
    # dependency_overrides YOK - gercek lifespan'in app.state.radar_service'i
    # kurdugunu dogrular (deps.get_radar_service'in okudugu yer).
    app = create_app(_settings())
    with TestClient(app) as client:
        resp = client.get("/radar")
    assert resp.status_code == 200
    assert resp.json()["detections"] == []
