from datetime import datetime, timezone

from ensemble.api.routers.radar import get_radar
from ensemble.api.schemas import RadarResponse
from ensemble.engine.radar import RadarService


def test_get_radar_returns_detections_and_updated_at():
    service = RadarService(github_port=None, judge_port=None)  # type: ignore
    result = get_radar(radar_service=service)
    # sozlesme §3: {detections: Detection[], updated_at} — artik tipli zarf (#20)
    assert isinstance(result, RadarResponse)
    assert result.detections == []
    assert result.updated_at.tzinfo is not None  # UTC gider, ceviri istemcide (Ek B5)
    assert result.updated_at <= datetime.now(timezone.utc)
