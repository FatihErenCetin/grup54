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

from pydantic import ValidationError

from ensemble.config import Settings
from ensemble.integrations.gemini.query_judge import _build_prompt
from ensemble.integrations.groq.client import GroqClient
from ensemble.integrations.groq.errors import GroqError
from ensemble.models import QueryDocument, QueryJudgement


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
            # Groq `response_format` yalnizca "gecerli JSON" garanti eder,
            # SEMAYI zorlamaz — bu yuzden dogrulama ihlali gercekci bir yol.
            # `GroqError`'a cevriliyor ki cagirandaki yedek mantigi bunu
            # "bu saglayici uretemedi" olarak gorsun; uydurma cevap URETILMEZ.
            raise GroqError(f"Groq Ask cevabi semaya uymuyor: {exc}") from exc
