"""YZ model secimi olcum harness'i (#244).

Amac: mevcut varsayilanlarin SECIMINI olcup gerekcelendirmek — DEGISTIRMEK
DEGIL. Iki eksen karsilastirilir:

1) **Judge yapilandirmasi** — `GEMINI_MODEL` icin >=2 aday (varsayilan:
   mevcut prod degeri `gemini-2.5-flash` + daha ucuz/hizli bir alternatif).
   Mevcut curated (#26) + backtest (#27) korpusu uzerinde `eval_runner`
   ile precision/recall/F0.5 + ortalama gecikme olculur.
2) **Embedding boyutu** — `GEMINI_EMBEDDING_DIMENSIONS` icin >=2 aday.
   Kucuk, SENTETIK (eval/datasets/ veya tests/fixtures/'a dokunmadan, elle
   yazilmis) bir "ilgili/ilgisiz metin cifti" orneklemi embed edilir; ilgili
   ciftlerin ortalama kosinus benzerligi ile ilgisiz ciftlerinkinin farki
   ("margin") boyutlar arasinda karsilastirilir.

    ⚠️ DIKKAT (#244 kapsam siniri): `GEMINI_EMBEDDING_DIMENSIONS=768` prod
    degeri pgvector `vector(768)` kolon tipine VE su an depoda duran TUM
    gomulu embedding'lere baglidir. Bu script/rapor prod degerini ASLA
    DEGISTIRMEZ — alternatif boyutlari yalniz GECICI, ayri bir `Settings`
    orneginde, olcum icin dener. `config.py`'deki varsayilan bu PR'da AYNI
    kalir.

MALIYET KONTROLU (kati, #244 talimati):
- Gercek Gemini cagrisi PARA harcar. `main()` ONCE agirliksiz (network'suz)
  tahmini toplam cagri sayisini hesaplar ve yazdirir.
- `GEMINI_API_KEY` (ortam/.env) YOKSA hicbir cagri denenmez — harness'in
  "tahmini sayi + rapor iskeleti" cikmasi KABUL EDILEBILIR bir sonuctur.
- `GEMINI_API_KEY` VARSA bile gercek cagri icin ayrica `--run` bayragi
  gerekir (savunma-derinligi: key varligi tek basina yeterli degil).
- Tahmini toplam `--max-calls` (varsayilan 200) sinirini asarsa calisma
  REDDEDILIR (`--judge-models`/`--embedding-dims` ile daraltilmali).

Kullanim:
    uv run python -m eval.model_secimi_eval            # yalniz tahmini yazdirir (agsiz)
    uv run python -m eval.model_secimi_eval --run       # GEMINI_API_KEY varsa gercek olcum
    make eval-model-secimi

Kanit/karar kaydi: bkz. `eval/model-secimi-raporu.md`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ensemble.config import Settings
from ensemble.engine.radar import SEMANTIC_SIMILARITY_TASK
from ensemble.engine.vectorstore import cosine_similarity
from ensemble.integrations.gemini.client import ResilientGeminiClient
from ensemble.integrations.gemini.embeddings import GeminiEmbeddingsAdapter
from ensemble.integrations.gemini.errors import GeminiError
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.gate import cheap_prejudge
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import JudgePort, JudgeUnavailableError
from eval.eval_runner import EvalRunner, load_backtest_corpus
from tests.fixtures.conflict_corpus import load_conflict_corpus

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RESULTS_PATH = _REPO_ROOT / "eval" / "model-secimi-sonuclar.json"

# Mevcut prod varsayilani ILK sirada — karsilastirma her zaman "su anki
# secime karsi" okunmali. Ikinci aday: daha ucuz/hizli bir alternatif.
DEFAULT_JUDGE_MODELS: tuple[str, ...] = ("gemini-2.5-flash", "gemini-2.5-flash-lite")

# Mevcut prod varsayilani (768) ILK sirada. gemini-embedding-001 Matryoshka
# (MRL) embedding oldugu icin output_dimensionality API parametresi zaten
# config.py'de var (bkz. integrations/gemini/client.py) — burada YALNIZCA
# olcum icin farkli degerler denenir, prod degeri degismez.
DEFAULT_EMBEDDING_DIMS: tuple[int, ...] = (768, 1536, 3072)

MAX_CALLS_DEFAULT = 200


# ---------------------------------------------------------------------------
# Sentetik embedding orneklemi — eval/datasets/ veya tests/fixtures/'a
# DOKUNULMADAN, elle yazilmis kucuk bir "ilgili/ilgisiz metin cifti" kumesi.
# Amac: gercek diff/hunk metni degil (kuratorlu/backtest korpusu ConflictCase
# seviyesinde ham diff metni TUTMAZ — veri sizintisi onlemi, bkz. eval/README.md),
# ama judge prompt'undaki dille ayni turden (kisa, Turkce, degisiklik ozeti)
# temsili bir prova. Boyutlar arasi AYRISTIRMA GUCU farkini olcmek icindir.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddingPair:
    text_a: str
    text_b: str
    related: bool
    note: str


EMBEDDING_SAMPLE: tuple[EmbeddingPair, ...] = (
    EmbeddingPair(
        text_a="Kullanıcı girişinde başarısız deneme sayısını sınırlayan rate-limit mantığı eklendi.",
        text_b="Login endpoint'ine istek başına deneme sınırlaması (rate limiting) getirildi.",
        related=True,
        note="ayni ozellik, farkli ifade",
    ),
    EmbeddingPair(
        text_a="Kullanıcı girişinde başarısız deneme sayısını sınırlayan rate-limit mantığı eklendi.",
        text_b="README dosyasındaki kurulum adımlarındaki yazım hatası düzeltildi.",
        related=False,
        note="alakasiz",
    ),
    EmbeddingPair(
        text_a="Radar servisi artık aynı yazarın farklı branch'lerini düşük öncelikli uyarıya çeviriyor.",
        text_b="Aynı geliştiricinin iki branch'i çakışma yerine low-severity bildirime dönüştürüldü.",
        related=True,
        note="ayni davranis degisikligi",
    ),
    EmbeddingPair(
        text_a="Radar servisi artık aynı yazarın farklı branch'lerini düşük öncelikli uyarıya çeviriyor.",
        text_b="Ödeme sağlayıcısı entegrasyonuna yeniden deneme (retry) mekanizması eklendi.",
        related=False,
        note="alakasiz",
    ),
    EmbeddingPair(
        text_a="Embedding önbelleğine TTL ve LRU tahliyesi eklendi, tekrarlanan Gemini çağrılarını azaltıyor.",
        text_b="Judge sonuçları için TTL tabanlı bir önbellek katmanı eklenerek tekrar eden sorgular önlendi.",
        related=True,
        note="ayni desen - cache",
    ),
    EmbeddingPair(
        text_a="Embedding önbelleğine TTL ve LRU tahliyesi eklendi, tekrarlanan Gemini çağrılarını azaltıyor.",
        text_b="Frontend tarafında board sayfasına tema filtreleme alanı eklendi.",
        related=False,
        note="alakasiz",
    ),
    EmbeddingPair(
        text_a="Webhook imzasını doğrulamadan önce gelen payload boyutu sınırlandırıldı.",
        text_b="GitHub webhook isteklerinde HMAC doğrulamasından önce gövde büyüklüğü sınırı eklendi.",
        related=True,
        note="ayni guvenlik onlemi",
    ),
    EmbeddingPair(
        text_a="Webhook imzasını doğrulamadan önce gelen payload boyutu sınırlandırıldı.",
        text_b="Sweep script'i artık ince ızgara (fine grid) seçeneğini destekliyor.",
        related=False,
        note="alakasiz",
    ),
)


def _unique_sample_texts(pairs: tuple[EmbeddingPair, ...] = EMBEDDING_SAMPLE) -> list[str]:
    """Ayni metin birden fazla ciftte gectigi icin TEK bir embed cagrisinda
    tekrar gonderilmesin diye essiz metinleri sirali dondurur."""
    seen: dict[str, None] = {}
    for pair in pairs:
        seen.setdefault(pair.text_a, None)
        seen.setdefault(pair.text_b, None)
    return list(seen)


# ---------------------------------------------------------------------------
# Judge yapilandirmasi karsilastirmasi
# ---------------------------------------------------------------------------


class _LatencyTrackingJudge:
    """Gercek Gemini'ye ULASAN cagrilari sayar + suresini olcer.

    `cheap_prejudge` (#24) agsiz bir on-yargidir — onu gecemeyen ciftler
    zaten gercek bir model cagrisi YAPMAZ (`FakeJudgeAdapter`/`GeminiJudgeAdapter`
    ikisi de kendi ici `judge_conflict`'inde ayni geçidi tekrar uygular; burada
    sayilan sayi, ALTTAKI implementasyon fake ya da gercek olsun, "gercek model
    cagrisina ULASACAK vaka sayisi" ile birebir ayni — tahmin icin de, gercek
    olcum icin de tek kaynak budur).

    GECIKME AYRISTIRMA (#257 bulgu 1 / #313): duvar-saati (`raw_durations`)
    tenacity'nin retry/backoff BEKLEMESINI de icerir — 429/5xx sonrasi 3
    denemeye kadar saniyeler suren backoff, olcumu "model hizi" degil "kota
    geri-cekilmesi" olcer hale getirebiliyordu (repro: stub'i her cagrida 429
    dondurecek sekilde kurup `avg_latency_s`'in ~1s'e ciktigini, gercek isin
    sifir oldugunu gozlemledik). `retry_client` (bir `ResilientGeminiClient`)
    verilirse, cagridan HEMEN SONRA `last_call_retry_wait_s`'i okuyup net
    calisma suresini (`durations`) bu bekleme suresinden ARINDIRIYORUZ;
    bekleme suresi de AYRI (`retry_wait_s`) raporlaniyor — ikisi karistirilmiyor.

    HATA GORUNURLUGU (#257 bulgu 1 / #313): `judge_conflict` `JudgeUnavailableError`
    firlatirsa (gercek modele ULASILDI ama basarisiz oldu — #252'den beri
    `_fallback_detection` YOK, hata sessizce degere donusmuyor) `errors` sayaci
    artar ve istisna YENIDEN firlatilir; cagiran (`run_judge_model_probe`) bunu
    model-basina yakalayip raporda GORUNUR kilar (bkz. o fonksiyonun docstring'i).
    """

    def __init__(self, inner: JudgePort, *, retry_client: ResilientGeminiClient | None = None) -> None:
        self._inner = inner
        self._retry_client = retry_client
        self.real_calls = 0
        self.errors = 0
        self.durations: list[float] = []  # NET calisma suresi — retry bekleme HARIC
        self.retry_wait_s: list[float] = []  # yalniz retry/backoff bekleme suresi
        self.raw_durations: list[float] = []  # duvar-saati (seffaflik icin — retry DAHIL)

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection:
        would_call_real_model = cheap_prejudge(a, b, overlap, sim) is None
        if not would_call_real_model:
            return self._inner.judge_conflict(a, b, overlap, sim)

        self.real_calls += 1
        start = time.perf_counter()
        try:
            result = self._inner.judge_conflict(a, b, overlap, sim)
        except JudgeUnavailableError:
            self.errors += 1
            raise
        raw_elapsed = time.perf_counter() - start
        retry_wait = self._retry_client.last_call_retry_wait_s if self._retry_client else 0.0
        self.raw_durations.append(raw_elapsed)
        self.retry_wait_s.append(retry_wait)
        self.durations.append(max(raw_elapsed - retry_wait, 0.0))
        return result


@dataclass(frozen=True)
class JudgeModelResult:
    """Tek bir judge modelinin olcum sonucu.

    `failed=True` ise P/R/F0.5/F1/tp/fp/fn/tn/total GECERSIZDIR (varsayilan
    0/0.0) — bu modelin olcumu tamamlanamadi, `error` alaninda NEDEN var.
    Eskiden (#252 oncesi) basarisiz bir model `_fallback_detection` ile
    makul-gorunen-ama-YANLIS bir P/R/F0.5 satiri uretiyordu (#257 bulgu 1);
    #252 bunu `JudgeUnavailableError` firlatmaya cevirdi ama bu sefer TEK bir
    basarisiz cagri TUM olcumu (diger modeller dahil) coktoruyordu (#257 bulgu
    4 ile ayni kok neden). Bu alan ikisinden de kacinir: basarisizlik SESSIZCE
    degere donusmez VE olcumun geri kalanini yok etmez — raporda ACIKCA gorunur.
    """

    model: str
    precision: float = 0.0
    recall: float = 0.0
    f05: float = 0.0
    f1: float = 0.0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    total: int = 0
    real_calls: int = 0
    avg_latency_s: float = 0.0  # NET — retry/backoff bekleme HARIC (#257 bulgu 1)
    avg_retry_wait_s: float = 0.0  # yalniz retry/backoff bekleme suresi — AYRI raporlanir
    error_count: int = 0  # gercek modele ULASIP basarisiz olan cagri sayisi
    failed: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "precision": self.precision,
            "recall": self.recall,
            "f05": self.f05,
            "f1": self.f1,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "total": self.total,
            "real_calls": self.real_calls,
            "avg_latency_s": self.avg_latency_s,
            "avg_retry_wait_s": self.avg_retry_wait_s,
            "error_count": self.error_count,
            "failed": self.failed,
            "error": self.error,
        }


def estimate_real_judge_calls() -> int:
    """Gercek Gemini'ye ULASACAK vaka sayisini AGSIZ hesaplar.

    `gate.py::run_gate()` ile AYNI operasyon noktasi (esiksiz, aynı-yazar
    dahil) — kalibre edilmis prod davranisini yansitir (eval/kalibrasyon-raporu.md).
    Tek judge yapilandirmasi icin gecerlidir; N model icin N ile carpilir.
    """
    tracker = _LatencyTrackingJudge(FakeJudgeAdapter())
    EvalRunner(judge=tracker).run_eval(use_backtest=True, use_curated=True)
    return tracker.real_calls


def run_judge_model_probe(
    models: tuple[str, ...],
    *,
    settings_factory=None,
    client_factory=None,
    on_result: Callable[[JudgeModelResult], None] | None = None,
) -> list[JudgeModelResult]:
    """Her aday `GEMINI_MODEL` icin TAM eval_runner koşusu — GERCEK Gemini cagrisi.

    `settings_factory(model) -> Settings` ve `client_factory(model) -> client`
    testte sahte istemci enjekte etmek icin override edilebilir (bkz.
    `tests/unit/test_provider_eval.py`'daki ayni desen). Varsayilan
    `Settings(GEMINI_MODEL=model)` — diger tum alanlar (GEMINI_API_KEY
    dahil) .env/ortamdan gelir.

    `client_factory` VERILMEZSE (gercek `--run` yolu) burada, GeminiJudgeAdapter'in
    HER cagrida yeniden kurdugu iceriden farkli olarak, TEK bir `ResilientGeminiClient`
    model basina kurulup TUM eval boyunca yeniden kullanilir — hem gereksiz SDK
    client kurulumunu (per-call) onler hem de `_LatencyTrackingJudge`'in retry
    bekleme suresini okuyabilmesi icin gereklidir (#257 bulgu 1 / #313).

    MODEL-BASINA HATA YAKALAMA + ARTIMLI RAPORLAMA (#257 bulgu 4 / #313): eskiden
    ikinci modeldeki TEK bir `JudgeUnavailableError` butun probu (birinci modelin
    ZATEN FATURALANMIS sonuclari dahil) coktuyordu. Artik her model AYRI
    try/except icinde kosuyor; basarisiz olan `failed=True` + `error=<mesaj>`
    ile ACIKCA isaretlenip devam ediliyor — onceki modellerin sonucu KAYBOLMAZ.
    `on_result` verilirse her model tamamlaninca (basarili/basarisiz FARK ETMEZ)
    cagrilir — `main()` bunu ARTIMLI diske yazmak icin kullanir.
    """
    factory = settings_factory or (lambda model: Settings(GEMINI_MODEL=model))
    results: list[JudgeModelResult] = []
    for model in models:
        settings = factory(model)
        tracked: _LatencyTrackingJudge | None = None
        try:
            if client_factory:
                client = client_factory(model)
                retry_client = client if isinstance(client, ResilientGeminiClient) else None
            else:
                client = ResilientGeminiClient(settings)
                retry_client = client
            tracked = _LatencyTrackingJudge(
                GeminiJudgeAdapter(settings, client=client), retry_client=retry_client
            )
            report = EvalRunner(judge=tracked).run_eval(use_backtest=True, use_curated=True)
        except (JudgeUnavailableError, GeminiError) as exc:
            result = JudgeModelResult(
                model=model,
                real_calls=tracked.real_calls if tracked else 0,
                error_count=tracked.errors if tracked else 0,
                failed=True,
                error=str(exc),
            )
        else:
            o = report.overall
            avg_latency = (
                sum(tracked.durations) / len(tracked.durations) if tracked.durations else 0.0
            )
            avg_retry_wait = (
                sum(tracked.retry_wait_s) / len(tracked.retry_wait_s)
                if tracked.retry_wait_s
                else 0.0
            )
            result = JudgeModelResult(
                model=model,
                precision=o.precision,
                recall=o.recall,
                f05=o.f05,
                f1=o.f1,
                tp=o.tp,
                fp=o.fp,
                fn=o.fn,
                tn=o.tn,
                total=o.total,
                real_calls=tracked.real_calls,
                avg_latency_s=round(avg_latency, 4),
                avg_retry_wait_s=round(avg_retry_wait, 4),
                error_count=tracked.errors,
                failed=False,
            )
        results.append(result)
        if on_result:
            on_result(result)
    return results


# ---------------------------------------------------------------------------
# Embedding boyutu karsilastirmasi
# ---------------------------------------------------------------------------


# pgvector `Vector` struct (src/vector.h): 4B vl_len_ + 2B dim + 2B unused
# header, ardindan boyut basina 4B float4 — pgvector'in kendi README'si
# bunu "4 * dimensions + 8 bytes" olarak belgeler. #244'un "embedding boyutu
# icin indeks/depolama boyutu" kabul kriteri (#257 bulgu 3 / #313): bu AGSIZ
# hesaplanabiliyordu ama ne olculmus ne "ÖLÇÜLEMEYENLER"e yazilmisti — sessiz
# atlanmisti. Repo icinde ANN indeksi (hnsw/ivfflat) YOK, yalniz duz
# `vector(N)` kolonu (migrations/versions/c4f1d6a2b8e9_vector_index_table.py,
# boyut `settings.GEMINI_EMBEDDING_DIMENSIONS` ile parametrik) — yani bu sayi
# ayni zamanda "indeks boyutu"nun ta kendisi.
_PGVECTOR_HEADER_BYTES = 8
_PGVECTOR_BYTES_PER_DIM = 4


def pgvector_storage_bytes(dimensions: int) -> int:
    """pgvector `vector(N)` kolonunun VEKTOR BASINA depolama boyutu (bayt).

    Saf fonksiyon — API anahtari YA DA ag cagrisi GEREKTIRMEZ; `--run`/
    `GEMINI_API_KEY` olmadan da (agsiz tahmin yolunda dahi) hesaplanabilir.
    """
    return _PGVECTOR_HEADER_BYTES + _PGVECTOR_BYTES_PER_DIM * dimensions


@dataclass(frozen=True)
class EmbeddingDimResult:
    """`failed=True` ise benzerlik/margin/gecikme GECERSIZDIR (bkz. `error`) —
    `storage_bytes` HER ZAMAN gecerlidir (ag gerektirmeyen saf hesap, #257
    bulgu 3 / #313). `JudgeModelResult.failed` ile ayni disiplin: model/boyut
    basina hata SESSIZCE yutulmaz, `failed`/`error` ile ACIKCA raporlanir
    (#257 bulgu 4 / #313)."""

    dimensions: int
    mean_related_sim: float = 0.0
    mean_unrelated_sim: float = 0.0
    margin: float = 0.0
    latency_s: float = 0.0
    n_pairs: int = 0
    storage_bytes: int = 0
    failed: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "dimensions": self.dimensions,
            "mean_related_sim": self.mean_related_sim,
            "mean_unrelated_sim": self.mean_unrelated_sim,
            "margin": self.margin,
            "latency_s": self.latency_s,
            "n_pairs": self.n_pairs,
            "storage_bytes": self.storage_bytes,
            "failed": self.failed,
            "error": self.error,
        }


def _pair_similarities(
    pairs: tuple[EmbeddingPair, ...], vectors_by_text: dict[str, list[float]]
) -> tuple[list[float], list[float]]:
    related_sims: list[float] = []
    unrelated_sims: list[float] = []
    for pair in pairs:
        sim = cosine_similarity(vectors_by_text[pair.text_a], vectors_by_text[pair.text_b])
        (related_sims if pair.related else unrelated_sims).append(sim)
    return related_sims, unrelated_sims


def run_embedding_dimension_probe(
    dims: tuple[int, ...],
    *,
    settings_factory=None,
    client_factory=None,
    pairs: tuple[EmbeddingPair, ...] = EMBEDDING_SAMPLE,
    on_result: Callable[[EmbeddingDimResult], None] | None = None,
) -> list[EmbeddingDimResult]:
    """Her aday boyut icin sentetik orneklemi embed eder — GERCEK Gemini cagrisi.

    Her boyut TEK bir batch cagrisi kullanir (essiz metinler tek `embed()`
    cagrisinda gonderilir) — cagri sayisi = `len(dims)`. `client_factory(dim)`
    testte sahte istemci enjekte etmek icin override edilebilir.

    BOYUT-BASINA HATA YAKALAMA + ARTIMLI RAPORLAMA (#257 bulgu 4 / #313): bir
    boyutun Gemini cagrisi basarisiz olursa (`GeminiError` ailesi — ag/kota/5xx)
    o boyut `failed=True` ile isaretlenip devam edilir; ONCEKI boyutlarin ZATEN
    FATURALANMIS sonuclari KAYBOLMAZ. `ValueError` (adapter essiz metin sayisi
    kadar vektor DONDURMEDI) BILEREK yakalanmiyor — bu dis bir API hatasi degil,
    adapter'in kendi SOZLESME ihlali/programlama hatasi; sessizce "bu boyut
    basarisiz" satirina indirgenirse gercek bir kod kusuru gizlenir (bkz.
    `tests/unit/test_model_secimi_eval.py::test_run_embedding_dimension_probe_raises_on_vector_count_mismatch`).
    """
    factory = settings_factory or (lambda dim: Settings(GEMINI_EMBEDDING_DIMENSIONS=dim))
    unique_texts = _unique_sample_texts(pairs)

    results: list[EmbeddingDimResult] = []
    for dim in dims:
        settings = factory(dim)
        client = client_factory(dim) if client_factory else None
        adapter = GeminiEmbeddingsAdapter(settings, client=client)
        start = time.perf_counter()
        try:
            vectors = adapter.embed(unique_texts, SEMANTIC_SIMILARITY_TASK)
        except GeminiError as exc:
            result = EmbeddingDimResult(
                dimensions=dim,
                storage_bytes=pgvector_storage_bytes(dim),
                failed=True,
                error=str(exc),
            )
            results.append(result)
            if on_result:
                on_result(result)
            continue
        latency = time.perf_counter() - start
        if len(vectors) != len(unique_texts):
            raise ValueError("embedding adapter essiz metin sayisi kadar vektor dondurmedi")

        vectors_by_text = dict(zip(unique_texts, vectors))
        related_sims, unrelated_sims = _pair_similarities(pairs, vectors_by_text)
        mean_related = sum(related_sims) / len(related_sims) if related_sims else 0.0
        mean_unrelated = sum(unrelated_sims) / len(unrelated_sims) if unrelated_sims else 0.0

        result = EmbeddingDimResult(
            dimensions=dim,
            mean_related_sim=round(mean_related, 4),
            mean_unrelated_sim=round(mean_unrelated, 4),
            margin=round(mean_related - mean_unrelated, 4),
            latency_s=round(latency, 4),
            n_pairs=len(pairs),
            storage_bytes=pgvector_storage_bytes(dim),
            failed=False,
        )
        results.append(result)
        if on_result:
            on_result(result)
    return results


# ---------------------------------------------------------------------------
# Maliyet tahmini
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallEstimate:
    judge_models: tuple[str, ...]
    embedding_dims: tuple[int, ...]
    real_calls_per_judge_config: int
    judge_call_total: int
    embedding_call_total: int
    grand_total: int
    max_retries: int  # Settings.GEMINI_MAX_RETRIES — worst-case carpani (#257 bulgu 2)
    worst_case_http_requests: int  # grand_total x max_retries — bkz. estimate_total_calls docstring


def estimate_total_calls(
    judge_models: tuple[str, ...],
    embedding_dims: tuple[int, ...],
    *,
    max_retries: int | None = None,
) -> CallEstimate:
    """`grand_total` MANTIKSAL (judge/embedding) cagriyi sayar, GERCEK HTTP
    istegini DEGIL (#257 bulgu 2 / #313). `ResilientGeminiClient` 429/5xx'te
    `GEMINI_MAX_RETRIES`'a (varsayilan 3) kadar tekrar dener — yani `--max-calls`
    tavani MANTIKSAL cagriyi sinirlar ama GERCEK istek sayisi bunun katina kadar
    cikabilir (olculdu: 8 mantiksal cagri -> 24 gercek istek, tam GEMINI_MAX_RETRIES
    kati). `worst_case_http_requests` bu ust siniri ACIKCA hesaplar — kullanici
    hangi sayiya imza attigini bilsin.
    """
    real_calls_per_config = estimate_real_judge_calls()
    judge_total = real_calls_per_config * len(judge_models)
    # Essiz metinler TEK batch cagrisinda gonderilir -> boyut basina 1 cagri.
    embedding_total = len(embedding_dims)
    grand_total = judge_total + embedding_total
    retries = max_retries if max_retries is not None else Settings().GEMINI_MAX_RETRIES
    return CallEstimate(
        judge_models=judge_models,
        embedding_dims=embedding_dims,
        real_calls_per_judge_config=real_calls_per_config,
        judge_call_total=judge_total,
        embedding_call_total=embedding_total,
        grand_total=grand_total,
        max_retries=retries,
        worst_case_http_requests=grand_total * retries,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_estimate(estimate: CallEstimate, max_calls: int) -> None:
    curated_n = len(load_conflict_corpus())
    backtest_n = len(load_backtest_corpus())
    print("=" * 60)
    print("  YZ model secimi olcum harness'i (#244) — tahmini cagri sayisi")
    print("=" * 60)
    print(f"  Judge aday(lar)i        : {list(estimate.judge_models)}")
    print(f"  Judge korpusu           : curated={curated_n} + backtest={backtest_n}"
          f" = {curated_n + backtest_n} vaka (orneklemesiz — zaten ucuz)")
    print(f"  On-gecitten (cheap_prejudge + esik) gercek modele ULASAN vaka"
          f" : {estimate.real_calls_per_judge_config}")
    print(f"  Tahmini judge cagrisi   : {estimate.real_calls_per_judge_config} x "
          f"{len(estimate.judge_models)} model = {estimate.judge_call_total}")
    print(f"  Embedding aday boyut(lar)i : {list(estimate.embedding_dims)}")
    print(f"  Embedding orneklemi     : {len(EMBEDDING_SAMPLE)} cift "
          f"({len(_unique_sample_texts())} essiz metin, sentetik — datasets/fixtures'a dokunulmadi)")
    print(f"  Tahmini embedding cagrisi : {len(estimate.embedding_dims)} boyut x 1 batch"
          f" = {estimate.embedding_call_total}")
    # #257 bulgu 3 / #313: depolama/indeks boyutu API anahtari GEREKTIRMEZ —
    # bu yuzden agsiz tahmin yolunda (key olmadan da) burada yazdiriliyor.
    storage_line = ", ".join(
        f"{dim}={pgvector_storage_bytes(dim)}bayt" for dim in estimate.embedding_dims
    )
    print(f"  Embedding depolama/indeks (agsiz, pgvector formulu) : {storage_line}")
    print(f"  TOPLAM tahmini cagri    : {estimate.grand_total}  (limit: {max_calls})")
    print(f"  EN KOTU DURUM (retry dahil, #257 bulgu 2) : {estimate.grand_total} x "
          f"GEMINI_MAX_RETRIES={estimate.max_retries} = {estimate.worst_case_http_requests} "
          "gercek HTTP istegi — 'TOPLAM tahmini cagri' MANTIKSAL sayidir, --max-calls")
    print("  bunu SINIRLAR ama 429/5xx retry'lari gercek istegi bu kata kadar cikarabilir "
          "(olculdu: 8 mantiksal -> 24 gercek, bkz. eval/model-secimi-raporu.md §2).")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YZ model secimi olcum harness'i (#244)")
    parser.add_argument(
        "--run",
        action="store_true",
        help="GEMINI_API_KEY varsa GERCEK cagriyi yapar (varsayilan: yalniz tahmini yazdirir)",
    )
    parser.add_argument("--max-calls", type=int, default=MAX_CALLS_DEFAULT)
    parser.add_argument(
        "--judge-models",
        default=",".join(DEFAULT_JUDGE_MODELS),
        help="virgullu GEMINI_MODEL adaylari",
    )
    parser.add_argument(
        "--embedding-dims",
        default=",".join(str(d) for d in DEFAULT_EMBEDDING_DIMS),
        help="virgullu GEMINI_EMBEDDING_DIMENSIONS adaylari",
    )
    args = parser.parse_args(argv)

    judge_models = tuple(m.strip() for m in args.judge_models.split(",") if m.strip())
    embedding_dims = tuple(int(d.strip()) for d in args.embedding_dims.split(",") if d.strip())

    estimate = estimate_total_calls(judge_models, embedding_dims)
    _print_estimate(estimate, args.max_calls)

    if estimate.grand_total > args.max_calls:
        print(
            f"  REDDEDILDI: tahmini {estimate.grand_total} cagri, limit {args.max_calls}'i "
            "asiyor. --judge-models / --embedding-dims ile daralt."
        )
        return 1

    settings_probe = Settings()
    if not settings_probe.GEMINI_API_KEY:
        print(
            "  GEMINI_API_KEY tanimli DEGIL (.env/ortam) — GERCEK CAGRI YAPILMAYACAK.\n"
            "  Bu KABUL EDILEBILIR bir sonuctur (#244 maliyet siniri): harness hazir,\n"
            "  key eklenince `--run` ile calistir. Rapor: eval/model-secimi-raporu.md"
        )
        return 0

    if not args.run:
        print(
            "  GEMINI_API_KEY bulundu ama --run VERILMEDI — guvenlik icin gercek cagri\n"
            "  yapilmiyor. Gercekten calistirmak icin:\n"
            "    uv run python -m eval.model_secimi_eval --run"
        )
        return 0

    print("  GEMINI_API_KEY bulundu + --run verildi — GERCEK Gemini cagrisi baslatiliyor...\n")

    # ARTIMLI YAZIM (#257 bulgu 4 / #313): her model/boyut TAMAMLANIR
    # TAMAMLANMAZ payload'a eklenip diske YAZILIR — sureç ikinci probda
    # coksa (ya da kesilse) bile ONCEKI, ZATEN FATURALANMIS sonuclar
    # `model-secimi-sonuclar.json`'da kalir, TUMDEN kaybolmaz.
    payload: dict = {"judge_models": [], "embedding_dims": []}

    def _persist() -> None:
        _RESULTS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print("  Judge yapilandirma sonuclari (tamamlandikca yaziliyor):")

    def _on_judge_result(r: JudgeModelResult) -> None:
        payload["judge_models"].append(r.to_dict())
        _persist()
        if r.failed:
            print(f"    {r.model}: BASARISIZ — {r.error} (gercek_cagri={r.real_calls})")
        else:
            print(
                f"    {r.model}: precision={r.precision:.4f} recall={r.recall:.4f} "
                f"f05={r.f05:.4f} gecikme_ort={r.avg_latency_s:.3f}s "
                f"(retry_bekleme_ort={r.avg_retry_wait_s:.3f}s, hata={r.error_count}) "
                f"(gercek_cagri={r.real_calls})"
            )

    judge_results = run_judge_model_probe(judge_models, on_result=_on_judge_result)

    print("\n  Embedding boyutu sonuclari (tamamlandikca yaziliyor):")

    def _on_embedding_result(r: EmbeddingDimResult) -> None:
        payload["embedding_dims"].append(r.to_dict())
        _persist()
        if r.failed:
            print(f"    dim={r.dimensions}: BASARISIZ — {r.error}")
        else:
            print(
                f"    dim={r.dimensions}: ilgili_sim_ort={r.mean_related_sim:.4f} "
                f"ilgisiz_sim_ort={r.mean_unrelated_sim:.4f} margin={r.margin:.4f} "
                f"gecikme={r.latency_s:.3f}s depolama={r.storage_bytes}bayt/vektor"
            )

    embedding_results = run_embedding_dimension_probe(
        embedding_dims, on_result=_on_embedding_result
    )

    print(f"\n  Sonuclar yazildi: {_RESULTS_PATH.relative_to(_REPO_ROOT)}")

    n_failed = sum(1 for r in judge_results if r.failed) + sum(
        1 for r in embedding_results if r.failed
    )
    if n_failed:
        print(
            f"  UYARI: {n_failed} prob BASARISIZ oldu (yukarida BASARISIZ satirlarina bak) — "
            "raporu bu durumu GORUNUR kilacak sekilde guncelle, basarisiz satiri sessizce atlama."
        )
    print("  eval/model-secimi-raporu.md dosyasini bu sayilarla GUNCELLE.")
    return 2 if n_failed else 0


if __name__ == "__main__":
    sys.exit(main())
