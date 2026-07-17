"""Gerçek Gemini çağrısına dayanan JudgePort implementasyonu (#24).

Rubrik-tabanlı prompt + Pydantic `response_schema` ile yapılandırılmış verdict.
Gemini'ye sormadan önce `cheap_prejudge` ile bilinen sınır durumlar (aynı actor,
yalnızca gürültü-dosyası overlap'i) elenir — maliyet kontrolü.
"""

from pydantic import BaseModel, ValidationError

from ensemble.config import Settings
from ensemble.integrations.gemini.client import ResilientGeminiClient
from ensemble.integrations.gemini.errors import GeminiError
from ensemble.integrations.gemini.gate import cheap_prejudge
from ensemble.models import Detection, NormalizedEvent


class _JudgeVerdict(BaseModel):
    severity: str
    confidence: float
    rationale: str


def _fallback_detection(a: NormalizedEvent, b: NormalizedEvent, reason: str) -> Detection:
    return Detection(
        id=f"{a.id}-{b.id}",
        actors=sorted({a.actor, b.actor}),
        branches=sorted({x for x in (a.branch, b.branch) if x}),
        files=sorted(set(a.files) & set(b.files)),
        severity="low",
        confidence=0.1,
        rationale=f"Gemini judge çağrısı başarısız oldu, düşük-güven varsayılan sonuç döndürüldü: {reason}",
    )


def _build_prompt(a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None) -> str:
    sim_text = f"{sim}" if sim is not None else "Bilinmiyor (yalnızca dosya kesişimi mevcut)"
    return (
        "İki GitHub olayı arasında GERÇEK bir çakışma olup olmadığını rubrik "
        "kriterleriyle değerlendir (her kriteri ayrı ayrı düşün):\n"
        "1) İki değişiklik aynı mantıksal birimi (fonksiyon/modül/sözleşme) mi değiştiriyor?\n"
        "2) İkisi de kod DAVRANIŞINI mı etkiliyor, yoksa biri biçimlendirme/yeniden "
        "adlandırma gibi mekanik bir değişiklik mi?\n"
        "3) Biri yalnızca üretilmiş/kilit dosyası gibi gürültü mü?\n"
        "Yukarıdaki kriterlere göre muhafazakar ol — emin değilsen düşük güven ver.\n\n"
        f"Olay A: actor={a.actor}, files={a.files}\n"
        f"Olay B: actor={b.actor}, files={b.files}\n"
        f"Kesişen dosyalar: {overlap}\n"
        f"Semantik benzerlik: {sim_text}\n"
    )


class GeminiJudgeAdapter:
    """`JudgePort` kontratının gerçek Gemini implementasyonu."""

    def __init__(self, settings: Settings, client: ResilientGeminiClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection:
        pre = cheap_prejudge(a, b, overlap, sim)
        if pre is not None:
            return pre

        try:
            client = self._client or ResilientGeminiClient(self._settings)
            raw = client.generate_content(
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
        except GeminiError as exc:
            return _fallback_detection(a, b, str(exc))
        except ValidationError as exc:
            return _fallback_detection(a, b, f"yanıt ayrıştırılamadı: {exc}")
