"""Groq tabanli JudgePort implementasyonu (#255).

Ayni rubrik prompt'unu `gemini/judge.py`'den PAYLASIR (`_build_prompt`) - iki
saglayici ayni soruyu sormali ki yedege dusuldugunde yargi olcutu degismesin.
Prompt'u kopyalamak, zamanla iki farkli rubrige (dolayisiyla ayni board'da iki
farkli severity anlayisina) yol acardi.

Ucuz on-yargi (`cheap_prejudge`) burada da calisir: gurultu-dosyasi ve
ayni-actor durumlari saglayiciya HIC gitmez. Yedek saglayicinin kotasini da
korumak icin gecit ONCE uygulanir.
"""

from pydantic import BaseModel, ValidationError

from ensemble.config import Settings
from ensemble.integrations.gemini.gate import cheap_prejudge
from ensemble.integrations.gemini.judge import _build_prompt
from ensemble.integrations.groq.client import GroqClient
from ensemble.integrations.groq.errors import GroqError
from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import JudgeUnavailableError


class _JudgeVerdict(BaseModel):
    severity: str
    confidence: float
    rationale: str


class GroqJudgeAdapter:
    """`JudgePort` kontratinin Groq implementasyonu."""

    def __init__(self, settings: Settings, client: GroqClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection:
        pre = cheap_prejudge(a, b, overlap, sim)
        if pre is not None:
            return pre

        try:
            client = self._client or GroqClient(self._settings)
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
        # #252 sozlesmesi: hata TESPIT URETMEZ. Groq `response_format` yalnizca
        # "gecerli JSON" garanti eder, semayi zorlamaz - bu yuzden dogrulama
        # ihlali burada gercekci bir yol ve o da sahte tespite DONUSTURULMEZ.
        except GroqError as exc:
            raise JudgeUnavailableError(f"{a.id}-{b.id}: Groq cagrisi basarisiz: {exc}") from exc
        except ValidationError as exc:
            raise JudgeUnavailableError(
                f"{a.id}-{b.id}: Groq yaniti semaya uymuyor: {exc}"
            ) from exc
