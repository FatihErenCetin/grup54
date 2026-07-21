import pytest
from pydantic import ValidationError

from ensemble.config import Settings
from ensemble.integrations.gemini.scope_judge import (
    FakeScopeJudgeAdapter,
    GeminiScopeJudgeAdapter,
    build_scope_judge,
)
from ensemble.models import ScopeCandidate, ScopeItemRef


class _Client:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""
        self.schema = None

    def generate_content(self, prompt: str, *, response_schema=None) -> str:
        self.prompt = prompt
        self.schema = response_schema
        return self.response


def _candidates() -> list[ScopeCandidate]:
    return [
        ScopeCandidate(
            evidence=ScopeItemRef(
                quote="IS-1: Scope-drift dedektörü", item_id="IS-1", section="in_scope"
            ),
            similarity=0.7,
        ),
        ScopeCandidate(
            evidence=ScopeItemRef(
                quote="NG-1: OAuth yazma", item_id="NG-1", section="non_goals"
            ),
            similarity=0.2,
        ),
    ]


def test_fake_scope_judge_guclu_in_scope_adayini_secer():
    result = FakeScopeJudgeAdapter().judge_scope("T-31", "scope motoru", _candidates())

    assert result.verdict == "in_scope"
    assert result.evidence_index == 0


def test_fake_scope_judge_guclu_non_goal_adayina_oncelik_verir():
    candidates = _candidates()
    candidates[1].similarity = 0.9

    result = FakeScopeJudgeAdapter().judge_scope("T-79", "oauth", candidates)

    assert result.verdict == "non_goal_violation"
    assert result.evidence_index == 1


def test_fake_scope_judge_zayif_eslesmede_drift_doner():
    candidates = _candidates()
    for candidate in candidates:
        candidate.similarity = 0.05

    result = FakeScopeJudgeAdapter().judge_scope("T-x", "alakasız", candidates)

    assert result.verdict == "drift"
    assert result.evidence_index is None


def test_gemini_scope_judge_structured_cevabi_ayristirir():
    client = _Client(
        '{"verdict":"in_scope","confidence":0.86,"evidence_index":0}'
    )
    adapter = GeminiScopeJudgeAdapter(
        Settings(_env_file=None, GEMINI_API_KEY="test"), client=client
    )

    result = adapter.judge_scope("T-31", "scope motoru", _candidates())

    assert result.verdict == "in_scope"
    assert "yalnız" in client.prompt.casefold()
    assert client.schema is not None


def test_gemini_scope_judge_bozuk_cevabi_verdict_gibi_gizlemez():
    client = _Client("not-json")
    adapter = GeminiScopeJudgeAdapter(
        Settings(_env_file=None, GEMINI_API_KEY="test"), client=client
    )

    with pytest.raises(ValidationError):
        adapter.judge_scope("T-31", "scope motoru", _candidates())


def test_scope_judge_factory_key_yoksa_fake():
    assert isinstance(
        build_scope_judge(Settings(_env_file=None)), FakeScopeJudgeAdapter
    )
