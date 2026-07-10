from google import genai
from google.genai import errors as genai_errors
from google.genai.types import HttpOptions
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from ensemble.config import Settings
from ensemble.integrations.gemini.errors import GeminiPermanentError, GeminiTransientError

_TRANSIENT_CODES = {408, 429, 500, 502, 503, 504}
_PERMANENT_CODES = {400, 401, 403, 404}


def _classify(exc: Exception) -> GeminiTransientError | GeminiPermanentError:
    """Ham SDK hatasını retry-karar noktası olan iki sınıftan birine çevirir."""
    code = getattr(exc, "code", None)
    if code in _PERMANENT_CODES:
        return GeminiPermanentError(str(exc))
    if code in _TRANSIENT_CODES:
        return GeminiTransientError(str(exc))
    # Sınıflandırılamayan hatalar (bağlantı kopması, timeout vb.) temkinli
    # olarak geçici sayılır — retry'a bir şans daha verilir.
    return GeminiTransientError(str(exc))


class ResilientGeminiClient:
    """Retry/backoff/timeout ile sarmalanmış Gemini istemcisi.

    Prompt/parse mantığı taşımaz — tek işi tek bir çağrıyı (`generate_content`)
    dayanıklı hale getirmektir. Judge/embeddings gibi üst katmanlar bunu kullanır.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.GEMINI_API_KEY:
            raise GeminiPermanentError("GEMINI_API_KEY tanımlı değil — .env kontrol et")
        self._settings = settings
        self._client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=HttpOptions(timeout=int(settings.GEMINI_TIMEOUT_S * 1000)),
        )

    def generate_content(self, prompt: str) -> str:
        return self._call_with_retry(prompt)

    def _call_with_retry(self, prompt: str) -> str:
        @retry(
            retry=retry_if_exception_type(GeminiTransientError),
            stop=stop_after_attempt(self._settings.GEMINI_MAX_RETRIES),
            wait=wait_random_exponential(multiplier=0.5, max=8),
            reraise=True,
        )
        def _attempt() -> str:
            try:
                response = self._client.models.generate_content(
                    model=self._settings.GEMINI_MODEL,
                    contents=prompt,
                )
            except genai_errors.APIError as exc:
                raise _classify(exc) from exc
            except Exception as exc:  # bağlantı kopması vb. SDK-dışı hatalar
                raise GeminiTransientError(str(exc)) from exc
            return response.text or ""

        return _attempt()
