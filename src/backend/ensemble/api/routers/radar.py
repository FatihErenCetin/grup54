from datetime import datetime, timezone

from fastapi import APIRouter

from ensemble.api.deps import RadarServiceDep
from ensemble.api.schemas import RadarDegraded, RadarResponse

router = APIRouter(prefix="/radar", tags=["radar"])


@router.get("")
def get_radar(radar_service: RadarServiceDep) -> RadarResponse:
    result = radar_service.collect()
    # ts UTC gider, cevirisi istemcide (Ek B5 konvansiyonu)
    return RadarResponse(
        detections=result.detections,
        updated_at=datetime.now(timezone.utc),
        # #252: yalnizca gercekten degerlendirilemeyen cift varsa doldurulur —
        # mutlu yolda alan `null` kalir.
        degraded=(
            RadarDegraded(
                judge_unavailable=result.judge_unavailable,
                evaluated=result.evaluated,
            )
            if result.judge_unavailable
            else None
        ),
    )
