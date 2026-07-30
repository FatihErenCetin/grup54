"""Ask (`/query`) icin Ollama judge — TAM-YEREL modun eksik yarisi (#334).

NEDEN VAR (bir GIZLILIK TAAHHUDU acigi):

`build_query_judge()`/`build_scope_judge()` yalniz IKI dal biliyordu —
`GEMINI_API_KEY` varsa Gemini, yoksa Fake. `LLM_PROVIDER` bu iki fonksiyonda
HIC okunmuyordu. Sonuc: `LLM_PROVIDER=ollama` secilmis bir kurulumda bile,
Gemini anahtari tanimliysa `/query` ve `/scope/check` BULUTA gidiyordu.

Karsilastirma: radar'in conflict judge'i bu konuda DOGRUydu (`app.py`'de
`LLM_PROVIDER == "ollama"` dali var). Yani taahhut ucte biri icin tutuluyor,
ucte ikisi icin tutulmuyordu — ve Ask prompt'u task/scope METINLERINI,
scope prompt'u kapsam MADDELERINI tasiyor.

Bir gizlilik iddiasi sessiz kalamaz: README taahhudu once kapsamla
sinirlandi (radar ile), simdi de bosluk gercekten kapaniyor.

PROMPT PAYLASILIR (`gemini/query_judge.py::_build_prompt`) — `groq/`
adaptorleriyle ayni ilke: uc saglayici da AYNI soruyu sormali ki saglayici
degisince cevabin OLCUTU degismesin.

SEMA ZORLAMASI: Ollama `format` alaninda GERCEK bir JSON semasi aliyor
(llama.cpp grameriyle kisitlanmis uretim) — yani Groq'un `json_object`'inin
aksine semayi ZORLUYOR. Yine de dogrulama burada yapiliyor: istemci
"tasima", judge "anlam" katmanidir ve model surumune gore davranis
degisebilir.
"""

from pydantic import ValidationError

from ensemble.config import Settings
from ensemble.integrations.gemini.query_judge import _build_prompt
from ensemble.integrations.ollama.client import OllamaClient
from ensemble.integrations.ollama.errors import OllamaError
from ensemble.models import QueryDocument, QueryJudgement


class OllamaQueryJudgeAdapter:
    """`QueryJudgePort` kontratinin Ollama (tam-yerel) implementasyonu."""

    def __init__(self, settings: Settings, client: OllamaClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def answer_query(self, question: str, documents: list[QueryDocument]) -> QueryJudgement:
        client = self._client or OllamaClient(self._settings)
        raw = client.generate_content(
            _build_prompt(question, documents), response_schema=QueryJudgement
        )
        try:
            return QueryJudgement.model_validate_json(raw)
        except ValidationError as exc:
            # `OllamaError`'a cevriliyor ki cagirandaki hata yolu bunu "bu
            # saglayici uretemedi" olarak gorsun; uydurma cevap URETILMEZ.
            raise OllamaError(f"Ollama Ask cevabi semaya uymuyor: {exc}") from exc
