"""Gerçek Gemini çağrısına dayanan JudgePort implementasyonu (#24).

Rubrik-tabanlı prompt + Pydantic `response_schema` ile yapılandırılmış verdict.
Gemini'ye sormadan önce `cheap_prejudge` ile bilinen sınır durumlar (aynı actor,
yalnızca gürültü-dosyası overlap'i) elenir — maliyet kontrolü.
"""

from pydantic import BaseModel

from ensemble.config import Settings
from ensemble.integrations.gemini.client import ResilientGeminiClient
from ensemble.integrations.gemini.errors import GeminiError
from ensemble.integrations.gemini.gate import cheap_prejudge
from ensemble.models import Detection, NormalizedEvent, Severity, severity_normalize
from ensemble.ports import JudgeUnavailableError


class _JudgeVerdict(BaseModel):
    # `str` DEGIL, `Severity` (#327): `response_schema` Gemini'ye gonderilen
    # yapisal cikti semasidir. `str` yazdigimizda API'ye "severity herhangi
    # bir metin olabilir" demis oluyorduk ve model `"High"` uretiyordu.
    # Literal, kisiti URETIM anina tasir — ayristirmada yakalamaktan iyidir.
    # Yine de `severity_normalize` savunma katmani olarak duruyor: Groq'un
    # `response_format`'i semayi ZORLAMAZ (bkz. groq/judge.py yorumu).
    severity: Severity
    confidence: float
    rationale: str


# NOT (#252): burada eskiden `_fallback_detection` vardı — hata durumunda
# severity="low"/confidence=0.1 bir Detection döndürüyordu. Bu bir fail-open'dı:
# "değerlendiremedik"i "çakışma değil"den ayırt edilemez hale getiriyor, cache'i
# 900 sn zehirliyor ve ham API hata metnini `rationale` üzerinden kullanıcı
# arayüzüne taşıyordu. Artık `JudgeUnavailableError` fırlatılıyor; ham hata
# yalnızca istisna mesajında (yani LOG'da) yaşar, kullanıcıya gitmez.


def _build_prompt(a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None) -> str:
    sim_text = f"{sim}" if sim is not None else "Bilinmiyor (yalnızca dosya kesişimi mevcut)"
    return (
        "İki GitHub olayı arasında GERÇEK bir çakışma olup olmadığını rubrik "
        "kriterleriyle değerlendir (her kriteri ayrı ayrı düşün):\n"
        "1) İki değişiklik aynı mantıksal birimi (fonksiyon/modül/sözleşme) mi değiştiriyor?\n"
        "2) İkisi de kod DAVRANIŞINI mı etkiliyor, yoksa biri biçimlendirme/yeniden "
        "adlandırma gibi mekanik bir değişiklik mi?\n"
        "3) Biri yalnızca üretilmiş/kilit dosyası gibi gürültü mü?\n"
        "Yukarıdaki kriterlere göre muhafazakar ol — emin değilsen düşük güven ver.\n"
        # #327: dagarciği ACIKCA yaz. Eskiden yalniz `response_schema`ya
        # guveniliyordu ve o sema `severity: str` oldugu icin model serbest
        # kaliyordu -> uretimde `"High"` yazdi, 1509 cift degerlendirilemedi.
        "severity alanı TAM OLARAK şu üç değerden biri olmalı (küçük harf): "
        "low, med, high.\n\n"
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
                severity=severity_normalize(verdict.severity),
                confidence=verdict.confidence,
                rationale=verdict.rationale,
            )
        except GeminiError as exc:
            raise JudgeUnavailableError(f"{a.id}-{b.id}: Gemini çağrısı başarısız: {exc}") from exc
        # `ValueError` (yalniz `ValidationError` DEGIL): pydantic'in
        # ValidationError'i ValueError alt sinifidir, yani bu tek cumle HEM
        # sema ihlalini HEM de severity_normalize'in "taninmayan severity"
        # hatasini yakalar (#327). Ikisi de ayni sonuca varir: yargi
        # UYDURULMAZ, cift degerlendirilememis sayilir.
        except ValueError as exc:
            raise JudgeUnavailableError(
                f"{a.id}-{b.id}: Gemini yanıtı şemaya uymuyor: {exc}"
            ) from exc
