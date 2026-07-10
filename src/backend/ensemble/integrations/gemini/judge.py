"""Gerçek Gemini çağrısına dayanan JudgePort implementasyonu.

Prompt ve yanıt-ayrıştırma burada kasıtlı olarak NAİFTİR — sınır durumlar
(edge case'ler, prompt inceliği) #24'ün işidir. Bu modülün sorumluluğu:
dayanıklı çağrı + hata durumunda çökme yerine yapılandırılmış, düşük-güven
bir Detection döndürmek ("structured error→verdict").
"""

import json

from ensemble.config import Settings
from ensemble.integrations.gemini.client import ResilientGeminiClient
from ensemble.integrations.gemini.errors import GeminiError
from ensemble.models import Detection, NormalizedEvent


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


def _build_prompt(a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float) -> str:
    return (
        "İki GitHub olayı arasında dosya çakışması olup olmadığını değerlendir.\n"
        f"Olay A: actor={a.actor}, files={a.files}\n"
        f"Olay B: actor={b.actor}, files={b.files}\n"
        f"Kesişen dosyalar: {overlap}\n"
        f"Semantik benzerlik: {sim}\n"
        'Yanıtı şu JSON şemasıyla ver: '
        '{"severity": "low|med|high", "confidence": 0..1, "rationale": "Türkçe açıklama"}'
    )


class GeminiJudgeAdapter:
    """`JudgePort` kontratının gerçek Gemini implementasyonu."""

    def __init__(self, settings: Settings, client: ResilientGeminiClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float
    ) -> Detection:
        try:
            client = self._client or ResilientGeminiClient(self._settings)
            raw = client.generate_content(_build_prompt(a, b, overlap, sim))
            parsed = json.loads(raw)
            return Detection(
                id=f"{a.id}-{b.id}",
                actors=sorted({a.actor, b.actor}),
                branches=sorted({x for x in (a.branch, b.branch) if x}),
                files=sorted(set(overlap)),
                severity=parsed["severity"],
                confidence=float(parsed["confidence"]),
                rationale=parsed["rationale"],
            )
        except GeminiError as exc:
            return _fallback_detection(a, b, str(exc))
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            return _fallback_detection(a, b, f"yanıt ayrıştırılamadı: {exc}")
