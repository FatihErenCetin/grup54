from threading import Lock

from ensemble.config import Settings
from ensemble.integrations.gemini.client import ResilientGeminiClient


class GeminiEmbeddingsAdapter:
    """Gemini-backed EmbeddingsPort implementation (#15)."""

    def __init__(
        self,
        settings: Settings,
        client: ResilientGeminiClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._client_lock = Lock()

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        return client.embed_content(texts, task_type=task_type)

    def _get_client(self) -> ResilientGeminiClient:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = ResilientGeminiClient(self._settings)
        return self._client
