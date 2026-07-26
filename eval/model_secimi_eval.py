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
from dataclasses import dataclass
from pathlib import Path

from ensemble.config import Settings
from ensemble.engine.radar import SEMANTIC_SIMILARITY_TASK
from ensemble.engine.vectorstore import cosine_similarity
from ensemble.integrations.gemini.embeddings import GeminiEmbeddingsAdapter
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.gate import cheap_prejudge
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import JudgePort
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
    """

    def __init__(self, inner: JudgePort) -> None:
        self._inner = inner
        self.real_calls = 0
        self.durations: list[float] = []

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection:
        would_call_real_model = cheap_prejudge(a, b, overlap, sim) is None
        if not would_call_real_model:
            return self._inner.judge_conflict(a, b, overlap, sim)

        self.real_calls += 1
        start = time.perf_counter()
        result = self._inner.judge_conflict(a, b, overlap, sim)
        self.durations.append(time.perf_counter() - start)
        return result


@dataclass(frozen=True)
class JudgeModelResult:
    model: str
    precision: float
    recall: float
    f05: float
    f1: float
    tp: int
    fp: int
    fn: int
    tn: int
    total: int
    real_calls: int
    avg_latency_s: float

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
) -> list[JudgeModelResult]:
    """Her aday `GEMINI_MODEL` icin TAM eval_runner koşusu — GERCEK Gemini cagrisi.

    `settings_factory(model) -> Settings` ve `client_factory(model) -> client`
    testte sahte istemci enjekte etmek icin override edilebilir (bkz.
    `tests/unit/test_provider_eval.py`'daki ayni desen). Varsayilan
    `Settings(GEMINI_MODEL=model)` — diger tum alanlar (GEMINI_API_KEY
    dahil) .env/ortamdan gelir; `client=None` ise adapter kendi
    `ResilientGeminiClient`'ini kurar (gercek cagri).
    """
    factory = settings_factory or (lambda model: Settings(GEMINI_MODEL=model))
    results: list[JudgeModelResult] = []
    for model in models:
        settings = factory(model)
        client = client_factory(model) if client_factory else None
        tracked = _LatencyTrackingJudge(GeminiJudgeAdapter(settings, client=client))
        report = EvalRunner(judge=tracked).run_eval(use_backtest=True, use_curated=True)
        o = report.overall
        avg_latency = (
            sum(tracked.durations) / len(tracked.durations) if tracked.durations else 0.0
        )
        results.append(
            JudgeModelResult(
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
            )
        )
    return results


# ---------------------------------------------------------------------------
# Embedding boyutu karsilastirmasi
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddingDimResult:
    dimensions: int
    mean_related_sim: float
    mean_unrelated_sim: float
    margin: float
    latency_s: float
    n_pairs: int

    def to_dict(self) -> dict:
        return {
            "dimensions": self.dimensions,
            "mean_related_sim": self.mean_related_sim,
            "mean_unrelated_sim": self.mean_unrelated_sim,
            "margin": self.margin,
            "latency_s": self.latency_s,
            "n_pairs": self.n_pairs,
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
) -> list[EmbeddingDimResult]:
    """Her aday boyut icin sentetik orneklemi embed eder — GERCEK Gemini cagrisi.

    Her boyut TEK bir batch cagrisi kullanir (essiz metinler tek `embed()`
    cagrisinda gonderilir) — cagri sayisi = `len(dims)`. `client_factory(dim)`
    testte sahte istemci enjekte etmek icin override edilebilir.
    """
    factory = settings_factory or (lambda dim: Settings(GEMINI_EMBEDDING_DIMENSIONS=dim))
    unique_texts = _unique_sample_texts(pairs)

    results: list[EmbeddingDimResult] = []
    for dim in dims:
        settings = factory(dim)
        client = client_factory(dim) if client_factory else None
        adapter = GeminiEmbeddingsAdapter(settings, client=client)
        start = time.perf_counter()
        vectors = adapter.embed(unique_texts, SEMANTIC_SIMILARITY_TASK)
        latency = time.perf_counter() - start
        if len(vectors) != len(unique_texts):
            raise ValueError("embedding adapter essiz metin sayisi kadar vektor dondurmedi")

        vectors_by_text = dict(zip(unique_texts, vectors))
        related_sims, unrelated_sims = _pair_similarities(pairs, vectors_by_text)
        mean_related = sum(related_sims) / len(related_sims) if related_sims else 0.0
        mean_unrelated = sum(unrelated_sims) / len(unrelated_sims) if unrelated_sims else 0.0

        results.append(
            EmbeddingDimResult(
                dimensions=dim,
                mean_related_sim=round(mean_related, 4),
                mean_unrelated_sim=round(mean_unrelated, 4),
                margin=round(mean_related - mean_unrelated, 4),
                latency_s=round(latency, 4),
                n_pairs=len(pairs),
            )
        )
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


def estimate_total_calls(
    judge_models: tuple[str, ...], embedding_dims: tuple[int, ...]
) -> CallEstimate:
    real_calls_per_config = estimate_real_judge_calls()
    judge_total = real_calls_per_config * len(judge_models)
    # Essiz metinler TEK batch cagrisinda gonderilir -> boyut basina 1 cagri.
    embedding_total = len(embedding_dims)
    return CallEstimate(
        judge_models=judge_models,
        embedding_dims=embedding_dims,
        real_calls_per_judge_config=real_calls_per_config,
        judge_call_total=judge_total,
        embedding_call_total=embedding_total,
        grand_total=judge_total + embedding_total,
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
    print(f"  TOPLAM tahmini cagri    : {estimate.grand_total}  (limit: {max_calls})")
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
    judge_results = run_judge_model_probe(judge_models)
    embedding_results = run_embedding_dimension_probe(embedding_dims)

    print("  Judge yapilandirma sonuclari:")
    for r in judge_results:
        print(
            f"    {r.model}: precision={r.precision:.4f} recall={r.recall:.4f} "
            f"f05={r.f05:.4f} gecikme_ort={r.avg_latency_s:.3f}s "
            f"(gercek_cagri={r.real_calls})"
        )

    print("\n  Embedding boyutu sonuclari:")
    for r in embedding_results:
        print(
            f"    dim={r.dimensions}: ilgili_sim_ort={r.mean_related_sim:.4f} "
            f"ilgisiz_sim_ort={r.mean_unrelated_sim:.4f} margin={r.margin:.4f} "
            f"gecikme={r.latency_s:.3f}s"
        )

    payload = {
        "judge_models": [r.to_dict() for r in judge_results],
        "embedding_dims": [r.to_dict() for r in embedding_results],
    }
    _RESULTS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  Sonuclar yazildi: {_RESULTS_PATH.relative_to(_REPO_ROOT)}")
    print("  eval/model-secimi-raporu.md dosyasini bu sayilarla GUNCELLE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
