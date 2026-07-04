from datetime import datetime

from fastapi import APIRouter

from ensemble.api.deps import RadarServiceDep
from ensemble.models import Detection

router = APIRouter(prefix="/radar", tags=["radar"])


@router.get("")
def get_radar(radar_service: RadarServiceDep) -> dict:
    detections: list[Detection] = radar_service.get_detections()
    return {
        "detections": detections,
        "updated_at": datetime.now().isoformat(),
    }
