from ensemble.api.routers.radar import get_radar
from ensemble.engine.embeddings import HashEmbeddings
from ensemble.engine.radar import RadarService
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.github.fake import FakeGitHubAdapter


def test_get_radar_returns_detections_and_updated_at():
    service = RadarService(
        github_port=FakeGitHubAdapter(events=[]),
        judge_port=FakeJudgeAdapter(),
        embeddings_port=HashEmbeddings(),
    )
    result = get_radar(radar_service=service)
    assert result["detections"] == []
    assert "updated_at" in result
