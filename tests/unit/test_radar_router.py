from ensemble.api.routers.radar import get_radar
from ensemble.engine.radar import RadarService


def test_get_radar_returns_detections_and_updated_at():
    service = RadarService(github_port=None, judge_port=None)  # type: ignore
    result = get_radar(radar_service=service)
    assert result["detections"] == []
    assert "updated_at" in result
