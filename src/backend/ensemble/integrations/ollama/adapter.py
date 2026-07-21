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
