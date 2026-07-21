from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from ensemble.config import Settings
from ensemble.integrations.ollama.errors import OllamaPermanentError, OllamaTransientError

_TRANSIENT_CODES = {408, 429, 500, 502, 503, 504}


class OllamaClient:
    """Ollama REST API istemcisi; prompt/judge semantigi tasimaz."""

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http_client or httpx.Client(
            base_url=settings.OLLAMA_BASE_URL,
            timeout=settings.OLLAMA_TIMEOUT_S,
        )

    def embed_content(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        """Bir metin batch'ini embed eder; task_type port uyumlulugu icindir."""
        del task_type  # Ollama /api/embed bu alani desteklemiyor.
        if not texts:
            return []
        payload = self._post_with_retry(
            "/api/embed",
            {"model": self._settings.OLLAMA_EMBEDDING_MODEL, "input": texts},
        )
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise OllamaPermanentError("Ollama her metin icin bir embedding dondurmedi")

        vectors: list[list[float]] = []
        for vector in embeddings:
            if not isinstance(vector, list) or not vector:
                raise OllamaPermanentError("Ollama embedding yaniti gecersiz")
            try:
                values = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise OllamaPermanentError("Ollama embedding degerleri sayisal degil") from exc
            if len(values) != self._settings.OLLAMA_EMBEDDING_DIMENSIONS:
                raise OllamaPermanentError(
                    "Ollama embedding boyutu "
                    f"{len(values)}, beklenen {self._settings.OLLAMA_EMBEDDING_DIMENSIONS}"
                )
            vectors.append(values)
        return vectors

    def generate_content(self, prompt: str, *, response_schema: type[BaseModel]) -> str:
        payload = self._post_with_retry(
            "/api/chat",
            {
                "model": self._settings.OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "format": response_schema.model_json_schema(),
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaPermanentError("Ollama chat yanitinda message.content yok")
        return content

    def _post_with_retry(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        @retry(
            retry=retry_if_exception_type(OllamaTransientError),
            stop=stop_after_attempt(self._settings.OLLAMA_MAX_RETRIES),
            wait=wait_random_exponential(multiplier=0.25, max=2),
            reraise=True,
        )
        def _attempt() -> dict[str, Any]:
            try:
                response = self._http.post(path, json=payload)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise OllamaTransientError("Ollama'ya baglanilamadi") from exc

            if response.status_code in _TRANSIENT_CODES:
                raise OllamaTransientError(f"Ollama gecici HTTP hatasi: {response.status_code}")
            if response.is_error:
                raise OllamaPermanentError(f"Ollama HTTP hatasi: {response.status_code}")
            try:
                data = response.json()
            except ValueError as exc:
                raise OllamaPermanentError("Ollama gecersiz JSON dondurdu") from exc
            if not isinstance(data, dict):
                raise OllamaPermanentError("Ollama JSON yaniti nesne degil")
            return data

        return _attempt()
