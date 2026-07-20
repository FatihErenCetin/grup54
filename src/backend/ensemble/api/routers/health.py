from fastapi import APIRouter

from ensemble.api.deps import RadarServiceDep, SettingsDep
from ensemble.api.schemas import HealthResponse
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.github.adapter import GitHubAdapter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(settings: SettingsDep, radar_service: RadarServiceDep) -> HealthResponse:
    # Acilis-anindaki wiring sonucunu okur (#53) - canli ag cagrisi yok, Fly
    # health-check'i aglamaz. GitHubAdapter/GeminiJudgeAdapter kurulduysa "ok",
    # Fake*'e dusulduyse "degraded" (app.py wiring, #159/#186).
    github_auth = "ok" if isinstance(radar_service.github_port, GitHubAdapter) else "degraded"
    gemini = "ok" if isinstance(radar_service.judge_port, GeminiJudgeAdapter) else "degraded"
    return HealthResponse(
        status="ok",
        mode=settings.ENSEMBLE_MODE,
        github_auth=github_auth,
        gemini=gemini,
    )
