from fastapi import APIRouter

from ensemble.api.deps import SettingsDep
from ensemble.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(status="ok", mode=settings.ENSEMBLE_MODE)
