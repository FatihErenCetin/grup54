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
    #
    # DEMO_MODE=true iken app.py::_build_judge_port judge'i CachedConflictJudge
    # (#63, engine/cache.py) ile SARMALAR - port artik GeminiJudgeAdapter degil,
    # CachedConflictJudge oluyor ve isinstance dogrudan hep "missing" derdi
    # (gercek regresyon: hosted demo /health hep gemini=missing raporlardi,
    # #189 make smoke kapisi kalici kirmizi kalirdi). Sarmalayicinin GERCEK
    # ic port'una in - CachedConflictJudge.inner (bkz. engine/cache.py) - sonra
    # isinstance uygula. Sarmalanmamis port'ta getattr fallback kendi degerine
    # doner (no-op).
    judge_port = getattr(radar_service.judge_port, "inner", radar_service.judge_port)
    github_auth = "configured" if isinstance(radar_service.github_port, GitHubAdapter) else "missing"
    gemini = "configured" if isinstance(judge_port, GeminiJudgeAdapter) else "missing"
    return HealthResponse(
        status="ok",
        mode=settings.ENSEMBLE_MODE,
        github_auth=github_auth,
        gemini=gemini,
    )
