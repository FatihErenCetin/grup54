import pytest

from ensemble.config import Settings
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.ollama.adapter import OllamaAdapter
from eval.provider_eval import (
    PROVIDER_THRESHOLDS,
    build_provider_judge,
    run_provider_eval,
)
from tests.fixtures.conflict_corpus import load_conflict_corpus


@pytest.mark.parametrize(
    ("provider", "settings", "expected_type"),
    [
        (
            "gemini",
            Settings(_env_file=None, LLM_PROVIDER="gemini", GEMINI_API_KEY="test"),
            GeminiJudgeAdapter,
        ),
        (
            "ollama",
            Settings(_env_file=None, LLM_PROVIDER="ollama"),
            OllamaAdapter,
        ),
    ],
)
def test_provider_eval_builds_both_provider_judges(provider, settings, expected_type):
    assert isinstance(build_provider_judge(provider, settings), expected_type)


class _StaticJudgeClient:
    def embed_content(self, texts, *, task_type):
        assert task_type == "SEMANTIC_SIMILARITY"
        return [[0.0] * 768 for _text in texts]

    def generate_content(self, _prompt, *, response_schema):
        assert response_schema is not None
        return '{"severity":"high","confidence":0.9,"rationale":"fixture"}'


class _ConservativeLocalClient(_StaticJudgeClient):
    def generate_content(self, _prompt, *, response_schema):
        assert response_schema is not None
        return '{"severity":"low","confidence":0.5,"rationale":"gri fixture"}'


@pytest.mark.parametrize("provider", ["gemini", "ollama"])
def test_same_calibration_fixture_runs_through_both_providers(provider, monkeypatch):
    import eval.eval_runner as runner_module
    import eval.provider_eval as provider_module

    case = next(case for case in load_conflict_corpus() if case.label == "conflict")
    monkeypatch.setattr(runner_module, "load_conflict_corpus", lambda: [case])
    monkeypatch.setattr(runner_module, "load_backtest_corpus", lambda: [])

    settings = Settings(_env_file=None, LLM_PROVIDER=provider, GEMINI_API_KEY="test")
    if provider == "gemini":
        judge = GeminiJudgeAdapter(settings, client=_StaticJudgeClient())
    else:
        judge = OllamaAdapter(settings, client=_StaticJudgeClient())
    monkeypatch.setattr(provider_module, "build_provider_judge", lambda *_args: judge)

    report, violations = run_provider_eval(provider, settings)

    assert report.overall.tp == 1
    assert report.overall.fp == 0
    assert any("toplam vaka" in violation for violation in violations)


def test_ollama_hybrid_baseline_meets_provider_gate(monkeypatch):
    import eval.provider_eval as provider_module

    settings = Settings(_env_file=None, LLM_PROVIDER="ollama")
    judge = OllamaAdapter(settings, client=_ConservativeLocalClient())
    monkeypatch.setattr(provider_module, "build_provider_judge", lambda *_args: judge)

    report, violations = run_provider_eval("ollama", settings)

    assert report.overall.tp == 5
    assert report.overall.fp == 0
    assert report.overall.fn == 3
    assert report.overall.tn == 110
    assert report.overall.f05 == 0.8929
    assert violations == []


def test_provider_threshold_profiles_are_independent_objects():
    assert set(PROVIDER_THRESHOLDS) == {"gemini", "ollama"}
    assert PROVIDER_THRESHOLDS["gemini"] is not PROVIDER_THRESHOLDS["ollama"]


def test_gemini_live_eval_requires_api_key():
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        build_provider_judge("gemini", Settings(_env_file=None, GEMINI_API_KEY=None))
