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

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        if not texts:
            return []
        client = self._client or ResilientGeminiClient(self._settings)
        return client.embed_content(texts, task_type=task_type)
