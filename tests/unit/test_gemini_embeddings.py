import pytest
from google.genai import types

from ensemble.config import Settings
from ensemble.integrations.gemini.client import ResilientGeminiClient
from ensemble.integrations.gemini.embeddings import GeminiEmbeddingsAdapter
from ensemble.integrations.gemini.errors import GeminiPermanentError, GeminiTransientError


class _StubEmbeddingClient:
    def __init__(self):
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def embed_content(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        self.calls.append((tuple(texts), task_type))
        return [[float(index), 1.0] for index, _text in enumerate(texts)]


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, GEMINI_API_KEY="fake-key", **overrides)


def test_gemini_embeddings_adapter_delegates_batch_and_task_type():
    client = _StubEmbeddingClient()
    adapter = GeminiEmbeddingsAdapter(_settings(), client=client)

    vectors = adapter.embed(["a", "b"], task_type="SEMANTIC_SIMILARITY")

    assert vectors == [[0.0, 1.0], [1.0, 1.0]]
    assert client.calls == [(("a", "b"), "SEMANTIC_SIMILARITY")]


def test_gemini_embeddings_adapter_empty_batch_skips_client():
    client = _StubEmbeddingClient()
    adapter = GeminiEmbeddingsAdapter(_settings(), client=client)

    assert adapter.embed([], task_type="SEMANTIC_SIMILARITY") == []
    assert client.calls == []


class _FakeApiError(Exception):
    def __init__(self, code: int):
        self.code = code
        super().__init__(f"api error {code}")


class _FakeEmbeddingModels:
    def __init__(self, fail_times: int = 0, fail_code: int = 503):
        self.fail_times = fail_times
        self.fail_code = fail_code
        self.calls = 0
        self.last_model = None
        self.last_contents = None
        self.last_config = None

    def embed_content(self, model: str, contents: list[str], config=None):
        self.calls += 1
        self.last_model = model
        self.last_contents = contents
        self.last_config = config
        if self.calls <= self.fail_times:
            raise _FakeApiError(self.fail_code)
        return types.EmbedContentResponse(
            embeddings=[
                types.ContentEmbedding(values=[float(index), 0.5])
                for index, _text in enumerate(contents)
            ]
        )


class _FakeSdkClient:
    def __init__(self, models: _FakeEmbeddingModels):
        self.models = models


def _patch_genai_client(monkeypatch, fake_models: _FakeEmbeddingModels) -> None:
    import ensemble.integrations.gemini.client as client_module

    monkeypatch.setattr(
        client_module.genai_errors, "APIError", _FakeApiError, raising=False
    )
    monkeypatch.setattr(
        client_module.genai,
        "Client",
        lambda **kwargs: _FakeSdkClient(fake_models),
    )


def test_resilient_client_embeds_with_model_task_type_and_dimensions(monkeypatch):
    fake_models = _FakeEmbeddingModels()
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(
        _settings(
            GEMINI_EMBEDDING_MODEL="gemini-embedding-001",
            GEMINI_EMBEDDING_DIMENSIONS=768,
        )
    )

    vectors = client.embed_content(["a", "b"], task_type="SEMANTIC_SIMILARITY")

    assert vectors == [[0.0, 0.5], [1.0, 0.5]]
    assert fake_models.last_model == "gemini-embedding-001"
    assert fake_models.last_contents == ["a", "b"]
    assert fake_models.last_config.task_type == "SEMANTIC_SIMILARITY"
    assert fake_models.last_config.output_dimensionality == 768


def test_resilient_client_embedding_retries_transient_errors(monkeypatch):
    fake_models = _FakeEmbeddingModels(fail_times=2, fail_code=503)
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(_settings(GEMINI_MAX_RETRIES=5))

    assert client.embed_content(["a"], task_type="SEMANTIC_SIMILARITY") == [[0.0, 0.5]]
    assert fake_models.calls == 3


def test_resilient_client_embedding_permanent_error_not_retried(monkeypatch):
    fake_models = _FakeEmbeddingModels(fail_times=10, fail_code=401)
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(_settings(GEMINI_MAX_RETRIES=5))

    with pytest.raises(GeminiPermanentError):
        client.embed_content(["a"], task_type="SEMANTIC_SIMILARITY")
    assert fake_models.calls == 1


def test_resilient_client_embedding_exhausts_transient_retries(monkeypatch):
    fake_models = _FakeEmbeddingModels(fail_times=10, fail_code=503)
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(_settings(GEMINI_MAX_RETRIES=3))

    with pytest.raises(GeminiTransientError):
        client.embed_content(["a"], task_type="SEMANTIC_SIMILARITY")
    assert fake_models.calls == 3


def test_resilient_client_rejects_short_embedding_batch(monkeypatch):
    class _ShortModels(_FakeEmbeddingModels):
        def embed_content(self, model: str, contents: list[str], config=None):
            self.calls += 1
            return types.EmbedContentResponse(
                embeddings=[types.ContentEmbedding(values=[1.0])]
            )

    fake_models = _ShortModels()
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(_settings())

    with pytest.raises(GeminiPermanentError, match="one vector per text"):
        client.embed_content(["a", "b"], task_type="SEMANTIC_SIMILARITY")
