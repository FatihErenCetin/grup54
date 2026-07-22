from datetime import UTC, datetime
import json

import httpx
import pytest

from ensemble.config import Settings
from ensemble.integrations.ollama.adapter import OllamaAdapter
from ensemble.integrations.ollama.client import OllamaClient
from ensemble.integrations.ollama.errors import OllamaPermanentError, OllamaTransientError
from ensemble.models import NormalizedEvent


def _settings(**overrides) -> Settings:
    values = {
        "LLM_PROVIDER": "ollama",
        "OLLAMA_EMBEDDING_DIMENSIONS": 2,
        "OLLAMA_MAX_RETRIES": 1,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def _client(handler, **settings_overrides) -> OllamaClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="http://127.0.0.1:11434",
    )
    return OllamaClient(_settings(**settings_overrides), http_client=http_client)


def _event(id_: str, actor: str) -> NormalizedEvent:
    return NormalizedEvent(
        id=id_,
        type="commit",
        actor=actor,
        branch="main",
        files=["src/core.py"],
        ts=datetime.now(UTC),
        ref=id_,
    )


def test_embed_uses_local_batch_endpoint_and_model():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    client = _client(handler)

    vectors = client.embed_content(["a", "b"], task_type="SEMANTIC_SIMILARITY")

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert seen["url"] == "http://127.0.0.1:11434/api/embed"
    assert seen["payload"] == {"model": "nomic-embed-text", "input": ["a", "b"]}


def test_embed_rejects_wrong_dimension():
    client = _client(lambda _request: httpx.Response(200, json={"embeddings": [[0.1]]}))

    with pytest.raises(OllamaPermanentError, match="boyutu"):
        client.embed_content(["a"], task_type="SEMANTIC_SIMILARITY")


def test_chat_requests_structured_non_streaming_output():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"severity":"high","confidence":0.9,"rationale":"x"}',
                }
            },
        )

    client = _client(handler)
    adapter = OllamaAdapter(_settings(), client=client)

    result = adapter.judge_conflict(
        _event("a", "esma"),
        _event("b", "fatih"),
        ["src/core.py"],
        0.45,
    )

    assert result.severity == "high"
    assert seen["model"] == "llama3.2"
    assert seen["stream"] is False
    assert seen["options"] == {"temperature": 0}
    assert seen["format"]["properties"]["severity"]["type"] == "string"
    assert seen["format"]["properties"]["severity"]["enum"] == ["low", "med", "high"]
    assert seen["messages"][0]["role"] == "user"


@pytest.mark.parametrize(
    ("overlap", "sim", "expected_severity", "expected_confidence"),
    [
        (["src/core.py"], 0.92, "high", 0.96),
        (["src/core.py"], 0.60, "med", 0.55),
        (["src/a.py", "src/b.py", "src/c.py"], 0.40, "high", 0.70),
        (["src/core.py"], None, "med", 0.40),
    ],
)
def test_calibrated_signal_policy_skips_unreliable_model_decision(
    overlap, sim, expected_severity, expected_confidence
):
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Kalibre sinyalde Ollama judge cagrilmamali")

    adapter = OllamaAdapter(_settings(), client=_client(handler))

    result = adapter.judge_conflict(
        _event("a", "esma"),
        _event("b", "fatih"),
        overlap,
        sim,
    )

    assert result.severity == expected_severity
    assert result.confidence == expected_confidence
    assert "Ollama yerel sinyal politikasi" in result.rationale


def test_transient_http_error_is_explicit_after_retry_budget():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "unavailable"})

    client = _client(handler, OLLAMA_MAX_RETRIES=2)

    with pytest.raises(OllamaTransientError, match="503"):
        client.embed_content(["a"], task_type="SEMANTIC_SIMILARITY")
    assert calls == 2


def test_permanent_http_error_is_not_retried():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"error": "model not found"})

    client = _client(handler, OLLAMA_MAX_RETRIES=3)

    with pytest.raises(OllamaPermanentError, match="404"):
        client.embed_content(["a"], task_type="SEMANTIC_SIMILARITY")
    assert calls == 1


def test_judge_failure_fails_low_without_cloud_fallback():
    client = _client(lambda _request: httpx.Response(500, json={"error": "down"}))
    adapter = OllamaAdapter(_settings(), client=client)

    result = adapter.judge_conflict(
        _event("a", "esma"),
        _event("b", "fatih"),
        ["src/core.py"],
        0.45,
    )

    assert result.severity == "low"
    assert result.confidence == 0.1
    assert "Gemini'ye dusmeden" in result.rationale


def test_same_actor_cheap_gate_skips_ollama_call():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Ollama cagrilmamali")

    adapter = OllamaAdapter(_settings(), client=_client(handler))

    result = adapter.judge_conflict(
        _event("a", "esma"),
        _event("b", "esma"),
        ["src/core.py"],
        0.9,
    )

    assert result.severity == "low"
