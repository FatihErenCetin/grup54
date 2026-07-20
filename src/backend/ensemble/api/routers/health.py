from fastapi import APIRouter

from ensemble.api.deps import RadarServiceDep, SettingsDep
from ensemble.api.schemas import HealthResponse
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.github.adapter import GitHubAdapter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(settings: SettingsDep, radar_service: RadarServiceDep) -> HealthResponse:
    # Acilis-anindaki WIRING sonucunu okur (#53) - canli ag cagrisi yok, Fly
    # health-check'i aglamaz. GitHubAdapter/GeminiJudgeAdapter kurulduysa
    # "configured", Fake*'e dusulduyse "missing" (app.py wiring, #159/#186).
    # "configured" DOGRULANMIS auth anlamina GELMEZ - yalniz kimlik bilgisi
    # SET EDILMIS (review bulgusu, Semih: gecersiz PEM/anahtarla da ayni
    # sonuc doner, gercek dogrulama ilk API cagrisina kadar bilinmez).
    github_auth = "configured" if isinstance(radar_service.github_port, GitHubAdapter) else "missing"
    gemini = "configured" if isinstance(radar_service.judge_port, GeminiJudgeAdapter) else "missing"
    return HealthResponse(
        status="ok",
        mode=settings.ENSEMBLE_MODE,
        github_auth=github_auth,
        gemini=gemini,
    )
