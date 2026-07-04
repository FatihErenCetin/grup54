from fastapi import APIRouter

from ensemble.api.deps import SettingsDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(settings: SettingsDep) -> dict:
    return {"status": "ok", "mode": settings.ENSEMBLE_MODE}
