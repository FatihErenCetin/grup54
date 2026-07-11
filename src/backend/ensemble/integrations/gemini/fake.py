"""Kural-tabanlı, tamamen deterministik JudgePort fake'i.

Ağ çağrısı yapmaz — offline/CI'da ve eval (#26-30) determinizmi için kullanılır.
Aynı girdi her zaman aynı Detection'ı üretir.
"""

from ensemble.integrations.gemini.gate import cheap_prejudge
from ensemble.models import Detection, NormalizedEvent

_HIGH_SIM = 0.8
_MED_SIM = 0.5
_HIGH_OVERLAP = 3


class FakeJudgeAdapter:
    """`JudgePort` kontratının deterministik, kural-tabanlı sahte implementasyonu."""

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float
    ) -> Detection:
        pre = cheap_prejudge(a, b, overlap, sim)
        if pre is not None:
            return pre

        n_overlap = len(overlap)

        if sim >= _HIGH_SIM or n_overlap >= _HIGH_OVERLAP:
            severity = "high"
            confidence = min(1.0, 0.5 + sim / 2)
        elif sim >= _MED_SIM:
            severity = "med"
            confidence = 0.4 + sim / 4
        else:
            severity = "low"
            confidence = 0.2

        rationale = (
            f"Kural-tabanlı fake: {n_overlap} dosya kesişimi, benzerlik={sim:.2f} "
            f"→ severity={severity}."
        )

        return Detection(
            id=f"{a.id}-{b.id}",
            actors=sorted({a.actor, b.actor}),
            branches=sorted({x for x in (a.branch, b.branch) if x}),
            files=sorted(overlap),
            severity=severity,
            confidence=round(confidence, 4),
            rationale=rationale,
        )
