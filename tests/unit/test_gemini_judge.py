from datetime import datetime

import pytest

from ensemble.config import Settings
from ensemble.integrations.gemini.client import ResilientGeminiClient
from ensemble.integrations.gemini.errors import GeminiPermanentError, GeminiTransientError
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter, _build_prompt
from ensemble.models import NormalizedEvent


def _event(id_: str, actor: str, files: list[str]) -> NormalizedEvent:
    return NormalizedEvent(
        id=id_, type="commit", actor=actor, branch="main", files=files, ts=datetime.now(), ref="abc"
    )


# ---------------------------------------------------------------------------
# FakeJudgeAdapter — deterministik, ağ çağrısı yok
# ---------------------------------------------------------------------------


def test_fake_deterministic_same_input_same_output():
    fake = FakeJudgeAdapter()
    a, b = _event("1", "esma", ["x.py"]), _event("2", "fatih", ["x.py"])
    d1 = fake.judge_conflict(a, b, overlap=["x.py"], sim=0.9)
    d2 = fake.judge_conflict(a, b, overlap=["x.py"], sim=0.9)
    assert d1 == d2


def test_fake_high_sim_gives_high_severity():
    fake = FakeJudgeAdapter()
    a, b = _event("1", "esma", ["x.py"]), _event("2", "fatih", ["x.py"])
    d = fake.judge_conflict(a, b, overlap=["x.py"], sim=0.9)
    assert d.severity == "high"


def test_fake_high_overlap_gives_high_severity():
    fake = FakeJudgeAdapter()
    a, b = _event("1", "esma", ["x.py", "y.py", "z.py"]), _event("2", "fatih", ["x.py", "y.py", "z.py"])
    d = fake.judge_conflict(a, b, overlap=["x.py", "y.py", "z.py"], sim=0.1)
    assert d.severity == "high"


def test_fake_low_sim_low_overlap_gives_low_severity():
    fake = FakeJudgeAdapter()
    a, b = _event("1", "esma", ["x.py"]), _event("2", "fatih", ["y.py"])
    d = fake.judge_conflict(a, b, overlap=[], sim=0.1)
    assert d.severity == "low"


def test_fake_same_actor_is_low_regardless_of_sim():
    fake = FakeJudgeAdapter()
    a, b = _event("1", "esma", ["x.py"]), _event("2", "esma", ["x.py"])
    d = fake.judge_conflict(a, b, overlap=["x.py"], sim=0.95)
    assert d.severity == "low"


def test_fake_lockfile_only_overlap_is_low_regardless_of_sim():
    fake = FakeJudgeAdapter()
    a, b = _event("1", "esma", ["uv.lock"]), _event("2", "fatih", ["uv.lock"])
    d = fake.judge_conflict(a, b, overlap=["uv.lock"], sim=0.9)
    assert d.severity == "low"


def test_fake_low_sim_with_overlap_is_low_not_med():
    # #50'deki eski bug: "or n_overlap > 0" her overlap'i med sayiyordu.
    fake = FakeJudgeAdapter()
    a, b = _event("1", "esma", ["config.py"]), _event("2", "fatih", ["config.py"])
    d = fake.judge_conflict(a, b, overlap=["config.py"], sim=0.15)
    assert d.severity == "low"


# ---------------------------------------------------------------------------
# GeminiJudgeAdapter — enjekte edilmiş stub client ile (gerçek ağ yok)
# ---------------------------------------------------------------------------


class _StubClient:
    def __init__(self, response: str | None = None, error: Exception | None = None):
        self._response = response
        self._error = error
        self.calls = 0
        self.last_response_schema = None

    def generate_content(self, prompt: str, *, response_schema=None) -> str:
        self.calls += 1
        self.last_response_schema = response_schema
        if self._error:
            raise self._error
        return self._response


def _settings() -> Settings:
    return Settings(_env_file=None, GEMINI_API_KEY="fake-key")


def test_judge_success_path_parses_response():
    stub = _StubClient(response='{"severity": "med", "confidence": 0.6, "rationale": "test"}')
    adapter = GeminiJudgeAdapter(_settings(), client=stub)
    a, b = _event("1", "esma", ["x.py"]), _event("2", "fatih", ["x.py"])
    d = adapter.judge_conflict(a, b, overlap=["x.py"], sim=0.5)
    assert d.severity == "med"
    assert d.confidence == 0.6
    assert stub.calls == 1


def test_judge_passes_response_schema_to_client():
    stub = _StubClient(response='{"severity": "low", "confidence": 0.2, "rationale": "x"}')
    adapter = GeminiJudgeAdapter(_settings(), client=stub)
    a, b = _event("1", "esma", ["x.py"]), _event("2", "fatih", ["x.py"])
    adapter.judge_conflict(a, b, overlap=["x.py"], sim=0.5)
    assert stub.last_response_schema is not None


def test_judge_prompt_marks_unknown_similarity():
    a, b = _event("1", "esma", ["x.py"]), _event("2", "fatih", ["x.py"])

    prompt = _build_prompt(a, b, overlap=["x.py"], sim=None)

    assert "Bilinmiyor (yalnızca dosya kesişimi mevcut)" in prompt


def test_judge_same_actor_skips_gemini_call_entirely():
    stub = _StubClient(response='{"severity": "high", "confidence": 0.9, "rationale": "x"}')
    adapter = GeminiJudgeAdapter(_settings(), client=stub)
    a, b = _event("1", "esma", ["x.py"]), _event("2", "esma", ["x.py"])
    d = adapter.judge_conflict(a, b, overlap=["x.py"], sim=0.95)
    assert d.severity == "low"
    assert stub.calls == 0


def test_judge_permanent_error_falls_back():
    stub = _StubClient(error=GeminiPermanentError("auth hatasi"))
    adapter = GeminiJudgeAdapter(_settings(), client=stub)
    a, b = _event("1", "esma", ["x.py"]), _event("2", "fatih", ["x.py"])
    d = adapter.judge_conflict(a, b, overlap=["x.py"], sim=0.5)
    assert d.severity == "low"
    assert d.confidence < 0.5


def test_judge_transient_error_exhausted_falls_back():
    stub = _StubClient(error=GeminiTransientError("timeout"))
    adapter = GeminiJudgeAdapter(_settings(), client=stub)
    a, b = _event("1", "esma", ["x.py"]), _event("2", "fatih", ["x.py"])
    d = adapter.judge_conflict(a, b, overlap=["x.py"], sim=0.5)
    assert d.severity == "low"


def test_judge_malformed_response_falls_back():
    stub = _StubClient(response="not json")
    adapter = GeminiJudgeAdapter(_settings(), client=stub)
    a, b = _event("1", "esma", ["x.py"]), _event("2", "fatih", ["x.py"])
    d = adapter.judge_conflict(a, b, overlap=["x.py"], sim=0.5)
    assert d.severity == "low"


# ---------------------------------------------------------------------------
# ResilientGeminiClient — retry/backoff, gerçek SDK'ya hiç dokunmadan
# ---------------------------------------------------------------------------


def test_client_missing_api_key_raises_permanent_without_network():
    settings = Settings(_env_file=None, GEMINI_API_KEY=None)
    with pytest.raises(GeminiPermanentError):
        ResilientGeminiClient(settings)


class _FakeApiError(Exception):
    def __init__(self, code: int):
        self.code = code
        super().__init__(f"api error {code}")


class _FakeModels:
    def __init__(self, fail_times: int, fail_code: int):
        self.fail_times = fail_times
        self.fail_code = fail_code
        self.calls = 0

    def generate_content(self, model: str, contents: str, config=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise _FakeApiError(self.fail_code)

        class _Resp:
            text = "ok"

        return _Resp()


class _FakeSdkClient:
    def __init__(self, models: _FakeModels):
        self.models = models


def _patch_genai_client(monkeypatch, fake_models: _FakeModels) -> None:
    import ensemble.integrations.gemini.client as client_module

    monkeypatch.setattr(
        client_module.genai_errors, "APIError", _FakeApiError, raising=False
    )
    monkeypatch.setattr(
        client_module.genai,
        "Client",
        lambda **kwargs: _FakeSdkClient(fake_models),
    )


def test_client_retries_then_succeeds(monkeypatch):
    fake_models = _FakeModels(fail_times=2, fail_code=503)
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(Settings(_env_file=None, GEMINI_API_KEY="k", GEMINI_MAX_RETRIES=5))
    result = client.generate_content("prompt")
    assert result == "ok"
    assert fake_models.calls == 3


def test_client_exhausts_retries_raises_transient(monkeypatch):
    fake_models = _FakeModels(fail_times=10, fail_code=503)
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(Settings(_env_file=None, GEMINI_API_KEY="k", GEMINI_MAX_RETRIES=3))
    with pytest.raises(GeminiTransientError):
        client.generate_content("prompt")
    assert fake_models.calls == 3


def test_client_permanent_error_not_retried(monkeypatch):
    fake_models = _FakeModels(fail_times=10, fail_code=401)
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(Settings(_env_file=None, GEMINI_API_KEY="k", GEMINI_MAX_RETRIES=5))
    with pytest.raises(GeminiPermanentError):
        client.generate_content("prompt")
    assert fake_models.calls == 1
