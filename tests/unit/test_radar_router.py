from datetime import datetime, timezone

from ensemble.api.routers.radar import get_radar
from ensemble.api.schemas import RadarResponse
from ensemble.engine.embeddings import HashEmbeddings
from ensemble.engine.radar import RadarService
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.models import NormalizedEvent
from ensemble.ports import JudgeUnavailableError


def test_get_radar_returns_detections_and_updated_at():
    service = RadarService(
        github_port=FakeGitHubAdapter(events=[]),
        judge_port=FakeJudgeAdapter(),
        embeddings_port=HashEmbeddings(),
    )
    result = get_radar(radar_service=service)
    # sozlesme §3: {detections: Detection[], updated_at} — artik tipli zarf (#20)
    assert isinstance(result, RadarResponse)
    assert result.detections == []
    assert result.updated_at.tzinfo is not None  # UTC gider, ceviri istemcide (Ek B5)
    assert result.updated_at <= datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# #252 — /radar yaniti "sonuc eksik"i GORUNUR kilar
# ---------------------------------------------------------------------------


class _KotaBitmisJudge:
    def judge_conflict(self, a, b, overlap, sim):
        raise JudgeUnavailableError(f"{a.id}-{b.id}: kota bitti (429)")


def _uc_olay():
    ayni = ["src/radar.py"]
    return [
        NormalizedEvent(
            id=eid, type="commit", actor=actor, branch=f"T-{eid}",
            files=ayni, ts=datetime.now(timezone.utc), ref="abc",
        )
        for eid, actor in (("a", "semih"), ("b", "enes"), ("c", "esma"))
    ]


def test_degraded_saglikli_yolda_null():
    """Mutlu yolda alan doldurulmaz — istemci tek kontrolle ayirir."""
    service = RadarService(
        github_port=FakeGitHubAdapter(events=[]),
        judge_port=FakeJudgeAdapter(),
        embeddings_port=HashEmbeddings(),
    )
    assert get_radar(radar_service=service).degraded is None


def test_judge_dustugunde_degraded_dolar_ve_tespit_uretilmez():
    """MUTASYON KILIDI: kota bitince yanit BOS ama SEBEBI belli olmali.

    Eski davranista burada 3 sahte tespit + null degraded donuyordu; yani
    yanit "3 cakisma buldum" diyordu. Simdi "0 buldum, 3 cifti
    degerlendiremedim" diyor — ayni arizanin durust ifadesi.
    """
    service = RadarService(
        github_port=FakeGitHubAdapter(events=_uc_olay()),
        judge_port=_KotaBitmisJudge(),
        embeddings_port=HashEmbeddings(),
        window_days=100_000,
    )
    result = get_radar(radar_service=service)

    assert result.detections == []
    assert result.degraded is not None
    assert result.degraded.judge_unavailable == 3
    assert result.degraded.evaluated == 0
