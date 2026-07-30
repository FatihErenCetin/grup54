"""Scope-drift (`/scope/check`) icin Ollama judge — tam-yerel mod (#334).

Gerekce ve prompt-paylasimi ilkesi icin bkz. `ollama/query_judge.py`
docstring'i. Bu ucun (radar · Ask · scope) sonuncusu: `LLM_PROVIDER=ollama`
secilmis bir kurulumda kapsam maddeleri artik makineden CIKMIYOR.
"""

from pydantic import ValidationError

from ensemble.config import Settings
from ensemble.integrations.gemini.scope_judge import _build_prompt
from ensemble.integrations.ollama.client import OllamaClient
from ensemble.integrations.ollama.errors import OllamaError
from ensemble.models import ScopeCandidate, ScopeJudgement


class OllamaScopeJudgeAdapter:
    """`ScopeJudgePort` kontratinin Ollama (tam-yerel) implementasyonu."""

    def __init__(self, settings: Settings, client: OllamaClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def judge_scope(
        self, ref: str, subject: str, candidates: list[ScopeCandidate]
    ) -> ScopeJudgement:
        client = self._client or OllamaClient(self._settings)
        raw = client.generate_content(
            _build_prompt(ref, subject, candidates), response_schema=ScopeJudgement
        )
        try:
            return ScopeJudgement.model_validate_json(raw)
        except ValidationError as exc:
            raise OllamaError(f"Ollama scope karari semaya uymuyor: {exc}") from exc
