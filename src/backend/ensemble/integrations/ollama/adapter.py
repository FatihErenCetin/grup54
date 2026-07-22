from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from ensemble.config import Settings
from ensemble.integrations.gemini.gate import cheap_prejudge
from ensemble.integrations.gemini.judge import _build_prompt
from ensemble.integrations.ollama.client import OllamaClient
from ensemble.integrations.ollama.errors import OllamaError
from ensemble.models import Detection, NormalizedEvent


class _JudgeVerdict(BaseModel):
    severity: Literal["low", "med", "high"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


_HIGH_SIMILARITY = 0.8
_MEDIUM_SIMILARITY = 0.5
_HIGH_OVERLAP_COUNT = 3


def _local_signal_detection(
    a: NormalizedEvent,
    b: NormalizedEvent,
    overlap: list[str],
    sim: float | None,
) -> Detection | None:
    """Kalibre yerel sinyalleri kucuk modele birakmadan karara cevirir.

    Canli llama3.2 kalibrasyonu acik pozitiflerin tamamini ``low`` verdi. Model
    yalniz actor/path/similarity gordugu icin sayisal karar sinirini guvenilir
    uygulayamiyor. Esikler FakeJudge ile kalibre edilen yerel baseline'la ayni;
    bu fonksiyon acik karar sinirlarini sonuclandirir, gri bolgeyi modele birakir.
    """
    overlap_count = len(overlap)
    if sim is None:
        if overlap_count >= _HIGH_OVERLAP_COUNT:
            severity: Literal["med", "high"] = "high"
            confidence = 0.5
        elif overlap_count > 0:
            severity = "med"
            confidence = 0.4
        else:
            return None
        sim_text = "bilinmiyor"
    elif sim >= _HIGH_SIMILARITY or overlap_count >= _HIGH_OVERLAP_COUNT:
        severity = "high"
        confidence = min(1.0, 0.5 + sim / 2)
        sim_text = f"{sim:.2f}"
    elif sim >= _MEDIUM_SIMILARITY:
        severity = "med"
        confidence = 0.4 + sim / 4
        sim_text = f"{sim:.2f}"
    else:
        return None

    return Detection(
        id=f"{a.id}-{b.id}",
        actors=sorted({a.actor, b.actor}),
        branches=sorted({x for x in (a.branch, b.branch) if x}),
        files=sorted(overlap),
        severity=severity,
        confidence=round(confidence, 4),
        rationale=(
            "Ollama yerel sinyal politikasi: "
            f"{overlap_count} dosya kesisimi, benzerlik={sim_text} -> severity={severity}."
        ),
    )


def _fallback_detection(a: NormalizedEvent, b: NormalizedEvent, reason: str) -> Detection:
    return Detection(
        id=f"{a.id}-{b.id}",
        actors=sorted({a.actor, b.actor}),
        branches=sorted({x for x in (a.branch, b.branch) if x}),
        files=sorted(set(a.files) & set(b.files)),
        severity="low",
        confidence=0.1,
        rationale=(
            "Ollama judge cagrisi basarisiz oldu; Gemini'ye dusmeden dusuk-guven "
            f"varsayilan sonuc donduruldu: {reason}"
        ),
    )


class OllamaAdapter:
    """EmbeddingsPort ve JudgePort'un tam-yerel Ollama implementasyonu."""

    def __init__(self, settings: Settings, client: OllamaClient | None = None) -> None:
        self._client = client or OllamaClient(settings)

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        return self._client.embed_content(texts, task_type=task_type)

    def judge_conflict(
        self,
        a: NormalizedEvent,
        b: NormalizedEvent,
        overlap: list[str],
        sim: float | None,
    ) -> Detection:
        pre = cheap_prejudge(a, b, overlap, sim)
        if pre is not None:
            return pre

        signal_detection = _local_signal_detection(a, b, overlap, sim)
        if signal_detection is not None:
            return signal_detection

        try:
            raw = self._client.generate_content(
                _build_prompt(a, b, overlap, sim), response_schema=_JudgeVerdict
            )
            verdict = _JudgeVerdict.model_validate_json(raw)
            return Detection(
                id=f"{a.id}-{b.id}",
                actors=sorted({a.actor, b.actor}),
                branches=sorted({x for x in (a.branch, b.branch) if x}),
                files=sorted(set(overlap)),
                severity=verdict.severity,
                confidence=verdict.confidence,
                rationale=verdict.rationale,
            )
        except OllamaError as exc:
            return _fallback_detection(a, b, str(exc))
        except ValidationError as exc:
            return _fallback_detection(a, b, f"yanit ayristirilamadi: {exc}")
