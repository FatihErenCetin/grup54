from fastapi.testclient import TestClient

from ensemble.api.routers.health import health_check
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.engine.embeddings import HashEmbeddings
from ensemble.engine.radar import RadarService
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.fake import FakeGitHubAdapter


def _radar_service(*, github_port, judge_port) -> RadarService:
    return RadarService(
        github_port=github_port,
        judge_port=judge_port,
        embeddings_port=HashEmbeddings(),
    )


def test_health_check_fake_adapterlerde_missing_raporlar():
    # sozlesme §3: {status, mode, github_auth, gemini} (#53 zenginlestirmesi)
    settings = Settings(ENSEMBLE_MODE="local")
    radar_service = _radar_service(github_port=FakeGitHubAdapter(), judge_port=FakeJudgeAdapter())
    result = health_check(settings=settings, radar_service=radar_service)
    assert result.model_dump() == {
        "status": "ok",
        "mode": "local",
        "github_auth": "missing",
        "gemini": "missing",
    }


def test_health_check_gercek_adapterlerde_configured_raporlar(tmp_path):
    pem = tmp_path / "app.pem"
    pem.write_text("fake-pem-icerigi")
    github_settings = Settings(
        _env_file=None,
        GITHUB_APP_ID="123",
        GITHUB_APP_PRIVATE_KEY_PATH=str(pem),
        GITHUB_APP_INSTALLATION_ID="456",
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
    )
    gemini_settings = Settings(_env_file=None, GEMINI_API_KEY="fake-key")
    radar_service = _radar_service(
        github_port=GitHubAdapter(github_settings),
        judge_port=GeminiJudgeAdapter(gemini_settings),
    )
    result = health_check(settings=Settings(ENSEMBLE_MODE="hosted"), radar_service=radar_service)
    assert result.github_auth == "configured"
    assert result.gemini == "configured"
    assert result.mode == "hosted"


def test_health_check_gecersiz_pem_de_configured_doner_dogrulanmis_degil(tmp_path):
    """Semih'in review bulgusu: 'configured' yalnizca kimlik bilgisi SET
    EDILMIS demektir, GECERLI demek DEGILDIR - GitHubAdapter construction'i
    PEM icerigini parse etmez (yalniz token yenilenirken okunur, #159).
    Bu test o sinirin BILEREK boyle kaldigini belgeler (canli dogrulama
    #58/spot-check kapsami)."""
    pem = tmp_path / "gecersiz.pem"
    pem.write_text("bu-gecerli-bir-pem-degil")
    github_settings = Settings(
        _env_file=None,
        GITHUB_APP_ID="123",
        GITHUB_APP_PRIVATE_KEY_PATH=str(pem),
        GITHUB_APP_INSTALLATION_ID="456",
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
    )
    radar_service = _radar_service(
        github_port=GitHubAdapter(github_settings), judge_port=FakeJudgeAdapter()
    )
    result = health_check(settings=Settings(ENSEMBLE_MODE="hosted"), radar_service=radar_service)
    assert result.github_auth == "configured"


def test_health_demo_modda_gercek_wiring_uzerinden_gemini_configured_raporlar(tmp_path):
    """E1/B1 regresyon kilidi: yukaridaki testler RadarService'i ELLE kurar,
    yani app.py::_build_judge_port'un DEMO_MODE=true iken judge'i
    CachedConflictJudge (#63) ile SARMALADIGI gercek wiring'i hic gormez - bu
    delik oradan sizdi (hosted demoda /health hep gemini=missing derdi).

    Bu test GERCEK create_app + lifespan yolundan geciyor: fix geri alinirsa
    (health.py'de getattr(...,"inner",...) unwrap'i kaldirilirsa) kirilir,
    cunku radar_service.judge_port artik dogrudan GeminiJudgeAdapter DEGIL,
    CachedConflictJudge olur ve isinstance dogrudan False doner."""
    db_path = tmp_path / "health-demo.db"
    settings = Settings(
        _env_file=None,
        DEMO_MODE=True,
        GEMINI_API_KEY="fake-key",
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
        DATABASE_URL=f"sqlite:///{db_path}",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["gemini"] == "configured"
    assert body["mode"] == "local"
