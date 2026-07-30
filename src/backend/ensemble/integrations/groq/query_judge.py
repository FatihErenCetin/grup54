"""Ask (`/query`) icin Groq judge — Gemini kotasi bitince devreye giren yedek (#330).

Neden var (uretimde olculdu, 2026-07-29): vizyondaki UC ornek sorunun UCU DE
canlida `503` donuyordu. D-53 (26 Tem) Groq'u yedek saglayici olarak dogru
karara baglamisti, ama duzeltme UC judge'dan YALNIZ birine (radar'in conflict
judge'i) uygulanmisti. Gemini ucretsiz kotasi olculdu: `gemini-2.5-flash`
**20 istek/GUN**. Radar o kotayi tuketiyor, `/query` ve `/scope/check` ciplak
kaliyor.

Prompt `gemini/query_judge.py`'den PAYLASILIR (`_build_prompt`) — `groq/judge.py`
ile ayni ilke: iki saglayici AYNI soruyu sormali ki yedege dusuldugunde cevabin
olcutu degismesin. Prompt'u kopyalamak zamanla iki farkli rubrige yol acardi.
"""

import json
import logging
import re

from pydantic import ValidationError

from ensemble.config import Settings
from ensemble.integrations.gemini.query_judge import _build_prompt
from ensemble.integrations.groq.client import GroqClient
from ensemble.integrations.groq.errors import GroqError
from ensemble.models import QueryDocument, QueryJudgement

logger = logging.getLogger("ensemble.groq.query")

# `engine/query.py::_CITATION_RE`'nin AYNISI. Kopya bilinçli: `integrations/`
# katmanı `engine/` içinden import etmez (katman disiplini). İkisinin aynı
# kaldığı testle kilitlenir (test_groq_query_judge.py) — sessizce ayrışmasın.
_CITATION_RE = re.compile(r"\[cite:([^\]\s]+)\]")


class GroqQueryJudgeAdapter:
    """`QueryJudgePort` kontratinin Groq implementasyonu."""

    def __init__(self, settings: Settings, client: GroqClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def answer_query(
        self, question: str, documents: list[QueryDocument]
    ) -> QueryJudgement:
        client = self._client or GroqClient(self._settings)
        raw = client.generate_content(
            _build_prompt(question, documents), response_schema=QueryJudgement
        )
        try:
            return QueryJudgement.model_validate_json(raw)
        except ValidationError as exc:
            onarilan = _eksik_alanlari_onar(raw)
            if onarilan is not None:
                logger.info(
                    "Groq eksik alanlı cevap döndürdü, metinden onarıldı (%d atıf)",
                    len(onarilan.citation_refs),
                )
                return onarilan
            # Groq `response_format` yalnizca "gecerli JSON" garanti eder,
            # SEMAYI zorlamaz — bu yuzden dogrulama ihlali gercekci bir yol.
            # `GroqError`'a cevriliyor ki cagirandaki yedek mantigi bunu
            # "bu saglayici uretemedi" olarak gorsun; uydurma cevap URETILMEZ.
            raise GroqError(f"Groq Ask cevabi semaya uymuyor: {exc}") from exc


def _eksik_alanlari_onar(raw: str) -> QueryJudgement | None:
    """Yalnız `answer` dönen bir Groq cevabını kurtarır; kurtaramazsa `None`.

    Canlıda ölçüldü (30 Tem 2026): llama-3.3-70b `{"answer": "... [cite:T-34]."}`
    döndürüp `citation_refs` ve `confidence`'ı atlıyordu. Cevabın KENDİSİ
    kullanılabilirdi — Gemini'nin günlük kotası bitmişken tek çalışan yolu
    biçimsel bir eksik yüzünden çöpe atmak pahalıydı.

    Onarımın sınırı NET, çünkü buradaki risk uydurmaya kaymak:

    - `citation_refs` UYDURULMAZ, modelin cevabına KENDİ yazdığı `[cite:...]`
      işaretlerinden OKUNUR. Model uydurma bir ref yazmışsa engine'in
      `_validated_citations`'ı zaten yakalar (kanıt kümesine karşı doğrular).
      Hiç işaret yoksa onarım YAPILMAZ — `None` döner, sağlayıcı düşmüş sayılır.
    - `confidence` bir YARGIdır ve model onu söylemedi; bu yüzden en düşük
      kademe (`low`) verilir. Bilinmeyen bir güveni "medium" saymak, kullanıcıya
      olmayan bir kesinlik satmak olurdu — eksik yönde yanılmak serbest, fazla
      yönde değil.
    """
    try:
        veri = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(veri, dict):
        return None
    answer = veri.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return None

    refs = veri.get("citation_refs")
    if not isinstance(refs, list) or not refs:
        # Sıra korunur, tekrarlar düşer — engine'in beklediği şekil.
        gorulen: set[str] = set()
        refs = []
        for ref in _CITATION_RE.findall(answer):
            if ref not in gorulen:
                gorulen.add(ref)
                refs.append(ref)
    if not refs:
        return None

    confidence = veri.get("confidence")
    if confidence not in ("low", "medium", "high"):
        confidence = "low"

    try:
        return QueryJudgement(answer=answer, citation_refs=refs, confidence=confidence)
    except ValidationError:
        return None
