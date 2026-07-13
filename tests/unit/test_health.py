from ensemble.api.routers.health import health_check
from ensemble.config import Settings


def test_health_check_returns_ok_and_mode():
    settings = Settings(ENSEMBLE_MODE="local")
    result = health_check(settings=settings)
    # sozlesme §3: {status, mode} — artik tipli zarf (#20); JSON cikti ayni
    assert result.model_dump() == {"status": "ok", "mode": "local"}
