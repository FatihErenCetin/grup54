"""Groq REST istemcisi (#255) — prompt/judge semantigi tasimaz.

Neden SDK degil httpx: Groq'un API'si OpenAI-uyumlu (`/openai/v1/chat/completions`)
ve tek bir POST'tan ibaret. `ollama/client.py` zaten ayni sekli httpx ile
kuruyor; ayni deseni izleyerek YENI BIR BAGIMLILIK eklemiyoruz. Bagimlilik
eklemek, yalnizca yedek saglayici icin tum kurulumun (CI, imaj, uv.lock)
yuzeyini genisletirdi.

Yapilandirilmis cikti: Groq `response_format={"type": "json_object"}` destekler
ama Gemini'nin `response_schema`'si gibi semayi ZORLAMAZ - yalnizca "gecerli
JSON" garantisi verir. Bu yuzden sema, prompt'a metin olarak da gomulur ve
dogrulama cagrian tarafta (judge.py) Pydantic ile yapilir. Sema ihlali
`GroqPermanentError` degil, judge katmaninda `JudgeUnavailableError` olur -
yani #252 sozlesmesi korunur: dogrulanamamis cikti TESPIT URETMEZ.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from ensemble.config import Settings
from ensemble.integrations.groq.errors import GroqPermanentError, GroqTransientError

_TRANSIENT_CODES = {408, 429, 500, 502, 503, 504}

# `gemini/client.py::RETRY_WAIT_CAP_S` ve `ollama/client.py` ile AYNI amac:
# tek noktadan okunan isimli sabit. `app.py::_groq_single_flight_wait_s` bir
# Groq cagrisinin GERCEK en-kotu-durum suresini bundan turetir; burada
# degisirse oradaki turetme de otomatik guncel kalir.
RETRY_WAIT_CAP_S = 2.0


class GroqClient:
    """Groq chat-completions istemcisi."""

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http_client or httpx.Client(
            base_url=settings.GROQ_BASE_URL,
            timeout=settings.GROQ_TIMEOUT_S,
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        )

    def generate_content(self, prompt: str, *, response_schema: type[BaseModel]) -> str:
        """Prompt'u gonderir, model yanitinin ham METNINI dondurur.

        Dogrulama BILEREK burada yapilmaz - `JudgePort` implementasyonu
        (judge.py) semayi dogrular ve ihlali `JudgeUnavailableError`'a cevirir.
        Istemci "tasima", judge "anlam" katmanidir.
        """
        payload = self._post_with_retry(
            "/openai/v1/chat/completions",
            {
                "model": self._settings.GROQ_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Yalnizca su JSON semasina UYAN tek bir JSON nesnesi dondur, "
                            "baska hicbir metin ekleme: "
                            + json.dumps(response_schema.model_json_schema(), ensure_ascii=False)
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise GroqPermanentError("Groq yanitinda choices yok")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise GroqPermanentError("Groq yanitinda message.content yok")
        return content

    def _post_with_retry(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        @retry(
            retry=retry_if_exception_type(GroqTransientError),
            stop=stop_after_attempt(self._settings.GROQ_MAX_RETRIES),
            wait=wait_random_exponential(multiplier=0.25, max=RETRY_WAIT_CAP_S),
            reraise=True,
        )
        def _attempt() -> dict[str, Any]:
            try:
                response = self._http.post(path, json=payload)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise GroqTransientError("Groq'a baglanilamadi") from exc

            if response.status_code in _TRANSIENT_CODES:
                raise GroqTransientError(f"Groq gecici HTTP hatasi: {response.status_code}")
            if response.is_error:
                raise GroqPermanentError(f"Groq HTTP hatasi: {response.status_code}")
            try:
                data = response.json()
            except ValueError as exc:
                raise GroqPermanentError("Groq gecersiz JSON dondurdu") from exc
            if not isinstance(data, dict):
                raise GroqPermanentError("Groq JSON yaniti nesne degil")
            return data

        return _attempt()
