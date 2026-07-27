from google import genai
from google.genai import errors as genai_errors
from google.genai.types import EmbedContentConfig, GenerateContentConfig, HttpOptions
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from ensemble.config import Settings
from ensemble.integrations.gemini.errors import (
    GeminiPermanentError,
    GeminiTransientError,
    sunucunun_bekleme_suresi,
)

_TRANSIENT_CODES = {408, 429, 500, 502, 503, 504}
_PERMANENT_CODES = {400, 401, 403, 404}

# `wait_random_exponential(multiplier=..., max=...)`'in üst sınırı - iki retry
# dekoratöründe (`_call_with_retry` + `_embed_with_retry`) AYNI olmalı (ikisi
# de tek noktadan okusun diye tek sabite çıkarıldı). #63 takip: `app.py::
# _gemini_single_flight_wait_s` bu sabiti, tek bir judge/embeddings çağrısının
# GERÇEK en-kötü-durum süresini türetmek için kullanır (bkz. o fonksiyonun
# docstring'i) - burada değişirse oradaki türetme de otomatik güncel kalır.
RETRY_WAIT_CAP_S = 8.0
# Gemini `batchEmbedContents` tek çağrıda en fazla 100 istek kabul eder
# (400 INVALID_ARGUMENT — üretimde ölçüldü, 2026-07-27). Sunucu tarafı bir
# tavan: ayar DEĞİL, o yüzden Settings'e değil buraya sabit yazılıyor.
_EMBED_BATCH_CAP = 100


def _classify(exc: Exception) -> GeminiTransientError | GeminiPermanentError:
    """Ham SDK hatasını retry-karar noktası olan iki sınıftan birine çevirir."""
    code = getattr(exc, "code", None)
    metin = str(exc)
    if code in _PERMANENT_CODES:
        return GeminiPermanentError(metin)
    # 429'da sunucu bekleme süresini SÖYLÜYOR; taşımazsak kendi tahminimizle
    # erken uyanır ve kotayı tekrar yakarız (üretimde ölçüldü — bkz.
    # `sunucunun_bekleme_suresi` docstring'i).
    if code in _TRANSIENT_CODES:
        return GeminiTransientError(metin, retry_after=sunucunun_bekleme_suresi(metin))
    # Sınıflandırılamayan hatalar (bağlantı kopması, timeout vb.) temkinli
    # olarak geçici sayılır — retry'a bir şans daha verilir. Bunlarda gövde
    # yok, dolayısıyla dayatılmış süre de yok.
    return GeminiTransientError(metin)


def _bekleme(varsayilan_wait, ust_sinir_saglayici=None):
    """Sunucunun dayattığı süre varsa ONU, yoksa normal backoff'u kullanır —
    ama İNSANIN BEKLEDİĞİ bir istekte üst sınırı aşmadan.

    tenacity'nin `wait` parametresi retry_state alan bir callable kabul eder;
    böylece bekleme kararını hatanın İÇERİĞİNE göre verebiliyoruz.

    ÜST SINIR NEDEN VAR (üretimde ölçüldü, 2026-07-27): `retryDelay`'e uymak
    toplu backfill'de doğru (`make rebuild` tam da bu sayede tamamlandı), ama
    interaktif `/radar` isteğinde YANLIŞ. O gün ölçülen canlı durum:

        Gemini kotası : generate_content 20 istek / GÜN  -> tükenmiş
        Groq yedeği   : 429
        retryDelay    : 23 sn
        /radar        : 66.7 sn

    Kota GÜNLÜK olduğu için 23 saniye beklemek hiçbir şey kazandırmıyordu —
    pencere yarın açılıyor. Kullanıcı 66 saniye bekleyip yine "değerlendiremedik"
    görüyordu. Erken pes edip DÜRÜST cevap vermek, geç pes edip aynı cevabı
    vermekten iyidir.

    Sınır ayardan okunur (`GEMINI_RETRY_AFTER_CAP_S`): `rebuild` gibi toplu
    işler yükseltip gerçekten bekleyebilir. `GITHUB_BACKFILL_LIMIT` ile
    `GITHUB_HISTORY_LIMIT` ayrımının aynısı — interaktif yol ile toplu yolun
    ihtiyacı farklı.
    """

    def _wait(retry_state) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        dayatilan = getattr(exc, "retry_after", None)
        if dayatilan:
            # +1 sn pay: kota penceresi tam sınırda açılıyorsa erken uyanıp
            # aynı duvara toslamayalım.
            istenen = float(dayatilan) + 1.0
            ust = ust_sinir_saglayici() if ust_sinir_saglayici else None
            return min(istenen, ust) if ust is not None else istenen
        return varsayilan_wait(retry_state)

    return _wait


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

    def generate_content(
        self, prompt: str, *, response_schema: type[BaseModel] | None = None
    ) -> str:
        return self._call_with_retry(prompt, response_schema=response_schema)

    def embed_content(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        """Gemini'nin 100-istek/batch tavanını aşmadan tüm metinleri gömer.

        Ölçüldü (üretim, 2026-07-27): #280 geçmiş backfill'i 250 olaya
        çıkarınca tek batch API'yi aştı ve `make rebuild` TAMAMEN düştü:

            400 INVALID_ARGUMENT — BatchEmbedContentsRequest.requests:
            at most 100 requests can be in one batch

        Tavan çağrı BAŞINA, toplam girdiye değil; parçalayıp birleştiriyoruz.
        Sıra KORUNUR — çağıran `texts[i]` ile `sonuç[i]`'yi eşleştiriyor, parça
        sınırında bir kayma vektörleri sessizce YANLIŞ olaya bağlardı (hata
        vermeden, yalnızca benzerlik skorlarını bozarak).
        """
        if not texts:
            return []
        vektorler: list[list[float]] = []
        for bas in range(0, len(texts), _EMBED_BATCH_CAP):
            parca = texts[bas : bas + _EMBED_BATCH_CAP]
            vektorler.extend(self._embed_with_retry(parca, task_type=task_type))
        return vektorler

    def _call_with_retry(
        self, prompt: str, *, response_schema: type[BaseModel] | None
    ) -> str:
        config = None
        if response_schema is not None:
            config = GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0,
            )

        @retry(
            retry=retry_if_exception_type(GeminiTransientError),
            stop=stop_after_attempt(self._settings.GEMINI_MAX_RETRIES),
            wait=_bekleme(
                wait_random_exponential(multiplier=0.5, max=RETRY_WAIT_CAP_S),
                lambda: self._settings.GEMINI_RETRY_AFTER_CAP_S,
            ),
            reraise=True,
        )
        def _attempt() -> str:
            try:
                response = self._client.models.generate_content(
                    model=self._settings.GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                )
            except genai_errors.APIError as exc:
                raise _classify(exc) from exc
            except Exception as exc:  # bağlantı kopması vb. SDK-dışı hatalar
                raise GeminiTransientError(str(exc)) from exc
            return response.text or ""

        return _attempt()

    def _embed_with_retry(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        config = EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self._settings.GEMINI_EMBEDDING_DIMENSIONS,
        )

        @retry(
            retry=retry_if_exception_type(GeminiTransientError),
            stop=stop_after_attempt(self._settings.GEMINI_MAX_RETRIES),
            wait=_bekleme(
                wait_random_exponential(multiplier=0.5, max=RETRY_WAIT_CAP_S),
                lambda: self._settings.GEMINI_RETRY_AFTER_CAP_S,
            ),
            reraise=True,
        )
        def _attempt() -> list[list[float]]:
            try:
                response = self._client.models.embed_content(
                    model=self._settings.GEMINI_EMBEDDING_MODEL,
                    contents=texts,
                    config=config,
                )
            except genai_errors.APIError as exc:
                raise _classify(exc) from exc
            except Exception as exc:
                raise GeminiTransientError(str(exc)) from exc

            embeddings = response.embeddings or []
            vectors: list[list[float]] = []
            for embedding in embeddings:
                if embedding.values is None:
                    raise GeminiPermanentError("Gemini embedding response missing values")
                vectors.append(list(embedding.values))
            if len(vectors) != len(texts):
                raise GeminiPermanentError(
                    "Gemini embeddings must return one vector per text"
                )
            return vectors

        return _attempt()
