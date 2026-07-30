"""Scope-drift (`/scope/check`) icin Groq judge — Gemini yedegi (#330).

Gerekce ve prompt-paylasimi ilkesi icin bkz. `groq/query_judge.py` docstring'i.
Canli olcum (29 Tem): `GET /scope/check?ref=T-33` -> `503 gemini_unavailable`,
`/scope/verdicts` bos. Kapsam bekcisi sifir kullanilabilirlikteydi.
"""

from pydantic import ValidationError

from ensemble.config import Settings
from ensemble.integrations.gemini.scope_judge import _build_prompt
from ensemble.integrations.groq.client import GroqClient
from ensemble.integrations.groq.errors import GroqError
from ensemble.models import ScopeCandidate, ScopeJudgement


class GroqScopeJudgeAdapter:
    """`ScopeJudgePort` kontratinin Groq implementasyonu."""

    def __init__(self, settings: Settings, client: GroqClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def judge_scope(
        self, ref: str, subject: str, candidates: list[ScopeCandidate]
    ) -> ScopeJudgement:
        client = self._client or GroqClient(self._settings)
        raw = client.generate_content(
            _build_prompt(ref, subject, candidates), response_schema=ScopeJudgement
        )
        try:
            return ScopeJudgement.model_validate_json(raw)
        except ValidationError as exc:
            raise GroqError(f"Groq scope karari semaya uymuyor: {exc}") from exc
