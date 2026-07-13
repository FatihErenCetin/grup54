from datetime import datetime, timezone

from fastapi import APIRouter

from ensemble.api.deps import RadarServiceDep
from ensemble.api.schemas import RadarResponse

router = APIRouter(prefix="/radar", tags=["radar"])


@router.get("")
def get_radar(radar_service: RadarServiceDep) -> RadarResponse:
    # ts UTC gider, cevirisi istemcide (Ek B5 konvansiyonu)
    return RadarResponse(
        detections=radar_service.get_detections(),
        updated_at=datetime.now(timezone.utc),
    )
