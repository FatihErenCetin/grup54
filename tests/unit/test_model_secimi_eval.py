"""YZ model secimi olcum harness'i (#244) testleri.

Gercek Gemini cagrisi YAPMAZ — `_StaticJudgeClient`/`_StaticEmbeddingClient`
enjekte edilir (bkz. `tests/unit/test_provider_eval.py`'daki ayni desen:
`GeminiJudgeAdapter`/`GeminiEmbeddingsAdapter` `client=None` degilse kendi
`ResilientGeminiClient`'ini hic kurmaz — GEMINI_API_KEY gerekmez).

#257 bulgu 1/2/3/4 (/ #313) icin ek testler asagida ayri bolumlerde: gecikme
ayristirma + hata gorunurlugu, maliyet en-kotu-durum, pgvector depolama
hesabi, model/boyut basina hata izolasyonu + artimli rapor.
"""

import json

import pytest

from ensemble.config import Settings
from ensemble.integrations.gemini.errors import GeminiTransientError
from eval.model_secimi_eval import (
    DEFAULT_EMBEDDING_DIMS,
    DEFAULT_JUDGE_MODELS,
    EMBEDDING_SAMPLE,
    EmbeddingDimResult,
    EmbeddingPair,
    JudgeModelResult,
    _unique_sample_texts,
    estimate_real_judge_calls,
    estimate_total_calls,
    main,
    pgvector_storage_bytes,
    run_embedding_dimension_probe,
    run_judge_model_probe,
)
from tests.fixtures.conflict_corpus import load_conflict_corpus


class _StaticJudgeClient:
    """embed_content cagrilirsa patlar - judge yolu embedding kullanmaz."""

    def __init__(self, severity: str, confidence: float) -> None:
        self._severity = severity
        self._confidence = confidence
        self.calls = 0

    def embed_content(self, texts, *, task_type):
        raise AssertionError("judge client embed_content cagrilmamali")

    def generate_content(self, _prompt, *, response_schema):
        assert response_schema is not None
        self.calls += 1
        return (
            f'{{"severity":"{self._severity}","confidence":{self._confidence},'
            '"rationale":"fixture"}'
        )


class _StaticEmbeddingClient:
    """generate_content cagrilirsa patlar - embedding yolu judge kullanmaz."""

    def __init__(self, vectors_by_text: dict[str, list[float]]) -> None:
        self._vectors_by_text = vectors_by_text
        self.calls = 0

    def generate_content(self, *args, **kwargs):
        raise AssertionError("embedding client generate_content cagrilmamali")

    def embed_content(self, texts, *, task_type):
        assert task_type == "SEMANTIC_SIMILARITY"
        self.calls += 1
        return [self._vectors_by_text[text] for text in texts]


# ---------------------------------------------------------------------------
# Sabit veri bütünlüğü — "en az iki" gereksinimleri (#244)
# ---------------------------------------------------------------------------


def test_default_judge_models_has_at_least_two():
    assert len(DEFAULT_JUDGE_MODELS) >= 2
    assert len(set(DEFAULT_JUDGE_MODELS)) == len(DEFAULT_JUDGE_MODELS)


def test_default_embedding_dims_has_at_least_two():
    assert len(DEFAULT_EMBEDDING_DIMS) >= 2
    assert len(set(DEFAULT_EMBEDDING_DIMS)) == len(DEFAULT_EMBEDDING_DIMS)


def test_embedding_sample_has_related_and_unrelated_pairs():
    related = [p for p in EMBEDDING_SAMPLE if p.related]
    unrelated = [p for p in EMBEDDING_SAMPLE if not p.related]
    assert len(related) >= 2
    assert len(unrelated) >= 2


def test_unique_sample_texts_dedupes():
    unique = _unique_sample_texts(EMBEDDING_SAMPLE)
    assert len(unique) == len(set(unique))
    # Her metin en az bir ciftte kullanildigi icin essiz sayi, 2x cift
    # sayisindan KUCUK olmali (tekrar eden text_a'lar var).
    assert len(unique) < 2 * len(EMBEDDING_SAMPLE)


# ---------------------------------------------------------------------------
# Maliyet tahmini (agsiz)
# ---------------------------------------------------------------------------


def test_estimate_real_judge_calls_matches_current_corpus():
    # #244: on-gecitten (cheap_prejudge + esik) gecen, gercek modele ULASAN
    # vaka sayisi. Bu sayi degisirse (korpus guncellenirse) test KASITLI
    # kirilir - eval/model-secimi-raporu.md'deki tahmin de yeniden hesaplanmali.
    assert estimate_real_judge_calls() == 8


def test_estimate_total_calls_arithmetic():
    estimate = estimate_total_calls(("model-a", "model-b"), (768, 1536, 3072))
    assert estimate.real_calls_per_judge_config == 8
    assert estimate.judge_call_total == 16
    assert estimate.embedding_call_total == 3
    assert estimate.grand_total == 19


def test_estimate_total_calls_well_under_budget_cap():
    estimate = estimate_total_calls(DEFAULT_JUDGE_MODELS, DEFAULT_EMBEDDING_DIMS)
    assert estimate.grand_total <= 200


# ---------------------------------------------------------------------------
# En kotu durum (retry dahil) maliyet tahmini (#257 bulgu 2 / #313)
# ---------------------------------------------------------------------------


def test_estimate_total_calls_worst_case_http_requests():
    # "Katı maliyet kontrolü" MANTIKSAL çağrıyı sayar, retry'lar --max-calls
    # tavanını GEMINI_MAX_RETRIES katına kadar aşabilir (ölçüldü: 8 mantıksal
    # -> 24 gerçek istek). Bu test o çarpımı KİLİTLER.
    estimate = estimate_total_calls(("model-a", "model-b"), (768, 1536, 3072), max_retries=3)
    assert estimate.max_retries == 3
    assert estimate.grand_total == 19
    assert estimate.worst_case_http_requests == 19 * 3 == 57


def test_estimate_total_calls_worst_case_defaults_to_settings_max_retries():
    # max_retries verilmezse Settings().GEMINI_MAX_RETRIES (varsayilan 3)
    # kullanilir — kullanici hicbir sey vermeden de en-kotu-durumu gorur.
    estimate = estimate_total_calls(("model-a",), (768,))
    assert estimate.max_retries == Settings().GEMINI_MAX_RETRIES
    assert estimate.worst_case_http_requests == estimate.grand_total * estimate.max_retries


# ---------------------------------------------------------------------------
# pgvector depolama/indeks boyutu (#257 bulgu 3 / #313) — agsiz, saf hesap
# ---------------------------------------------------------------------------


def test_pgvector_storage_bytes_matches_documented_formula():
    # pgvector README: "4 * dimensions + 8 bytes" (Vector struct: 4B vl_len_
    # + 2B dim + 2B unused header + boyut basina 4B float4).
    assert pgvector_storage_bytes(768) == 3080
    assert pgvector_storage_bytes(1536) == 6152
    assert pgvector_storage_bytes(3072) == 12296


def test_pgvector_storage_bytes_ratios_match_1x_2x_4x_claim():
    # #244'un "embedding boyutu icin indeks/depolama boyutu" kabul kriteri:
    # 1536/3072'nin mevcut prod (768) degerine gore yaklasik 2x/4x oldugunu
    # dogrular (kucuk sabit header nedeniyle TAM degil, ~%0.3 sapma).
    base = pgvector_storage_bytes(768)
    assert pgvector_storage_bytes(1536) / base == pytest.approx(2, rel=0.01)
    assert pgvector_storage_bytes(3072) / base == pytest.approx(4, rel=0.01)


# ---------------------------------------------------------------------------
# Judge yapilandirma probu
# ---------------------------------------------------------------------------


def test_run_judge_model_probe_counts_only_real_calls(monkeypatch):
    import eval.eval_runner as runner_module

    case = next(c for c in load_conflict_corpus() if c.label == "conflict")
    monkeypatch.setattr(runner_module, "load_conflict_corpus", lambda: [case])
    monkeypatch.setattr(runner_module, "load_backtest_corpus", lambda: [])

    client = _StaticJudgeClient(severity="high", confidence=0.9)
    settings = Settings(_env_file=None, GEMINI_API_KEY="test")

    results = run_judge_model_probe(
        ("gemini-2.5-flash",),
        settings_factory=lambda _model: settings,
        client_factory=lambda _model: client,
    )

    assert len(results) == 1
    result = results[0]
    assert result.model == "gemini-2.5-flash"
    assert result.real_calls == 1
    assert result.tp == 1
    assert result.total == 1
    assert client.calls == 1
    assert result.avg_latency_s >= 0.0


def test_run_judge_model_probe_two_configs_can_diverge(monkeypatch):
    """Iki farkli 'model' (burada aslinda iki farkli sahte cevap) farkli
    metrikler uretebilmeli - probun asil amaci budur."""
    import eval.eval_runner as runner_module

    case = next(c for c in load_conflict_corpus() if c.label == "conflict")
    monkeypatch.setattr(runner_module, "load_conflict_corpus", lambda: [case])
    monkeypatch.setattr(runner_module, "load_backtest_corpus", lambda: [])

    clients = {
        "aggressive": _StaticJudgeClient(severity="high", confidence=0.9),
        "conservative": _StaticJudgeClient(severity="low", confidence=0.2),
    }
    settings = Settings(_env_file=None, GEMINI_API_KEY="test")

    results = run_judge_model_probe(
        ("aggressive", "conservative"),
        settings_factory=lambda _model: settings,
        client_factory=lambda model: clients[model],
    )

    by_model = {r.model: r for r in results}
    assert by_model["aggressive"].tp == 1
    assert by_model["aggressive"].fn == 0
    assert by_model["conservative"].tp == 0
    assert by_model["conservative"].fn == 1


class _AlwaysFailingJudgeClient:
    """Her cagrida basarisiz olur - tamamen coken bir 'model' simulasyonu.

    `GeminiJudgeAdapter` enjekte edilmis stub'i DOGRUDAN cagirir (retry
    ResilientGeminiClient'e ozgudur, bkz. tests/unit/test_gemini_judge.py
    yorumu) — yani bu, retry SONRASI da kurtulamayan bir modeli temsil eder.
    """

    def generate_content(self, prompt, *, response_schema):
        raise GeminiTransientError("429 RESOURCE_EXHAUSTED (simulasyon)")


def test_run_judge_model_probe_isolates_failing_model(monkeypatch):
    """(#257 bulgu 1 + 4 / #313) Bir modelin TAM basarisizligi (a) diger
    modelin ZATEN FATURALANMIS sonucunu YOK ETMEZ, (b) raporda "makul"
    gorunen bir P/R/F0.5 satiri UYDURMAZ — `failed=True` + `error` ile
    ACIKCA isaretlenir.

    MUTASYON KANITI: `run_judge_model_probe`'daki model-basina try/except
    kaldirilirsa (eski davranis) bu cagri `JudgeUnavailableError` ile COKER
    ve `gemini-2.5-flash`'in ZATEN hesaplanmis sonucu da kaybolur — asagidaki
    ilk assert bloğu bu durumda hic calismaz (fonksiyon exception firlatir).
    """
    import eval.eval_runner as runner_module

    case = next(c for c in load_conflict_corpus() if c.label == "conflict")
    monkeypatch.setattr(runner_module, "load_conflict_corpus", lambda: [case])
    monkeypatch.setattr(runner_module, "load_backtest_corpus", lambda: [])

    working = _StaticJudgeClient(severity="high", confidence=0.9)
    failing = _AlwaysFailingJudgeClient()
    settings = Settings(_env_file=None, GEMINI_API_KEY="test")

    results = run_judge_model_probe(
        ("gemini-2.5-flash", "gemini-2.5-flash-lite"),
        settings_factory=lambda _model: settings,
        client_factory=lambda model: working if model == "gemini-2.5-flash" else failing,
    )

    by_model = {r.model: r for r in results}
    assert len(results) == 2  # HER IKI model de raporda VAR — biri crash etmedi

    ok = by_model["gemini-2.5-flash"]
    assert ok.failed is False
    assert ok.tp == 1
    assert ok.total == 1

    bad = by_model["gemini-2.5-flash-lite"]
    assert bad.failed is True
    assert bad.error is not None
    assert "429" in bad.error
    # Basarisiz modelin metrikleri "gercek olcum" GIBI GORUNMUYOR — hepsi
    # varsayilan/gecersiz (#252-oncesi _fallback_detection'in tam tersi).
    assert bad.precision == 0.0
    assert bad.total == 0


def test_run_judge_model_probe_on_result_fires_per_model_incrementally(monkeypatch):
    """(#257 bulgu 4 / #313) `on_result` her model TAMAMLANDIKCA cagrilir —
    `main()` bunu diske ARTIMLI yazmak icin kullanir (odenmis sonuc kaybolmaz)."""
    import eval.eval_runner as runner_module

    case = next(c for c in load_conflict_corpus() if c.label == "conflict")
    monkeypatch.setattr(runner_module, "load_conflict_corpus", lambda: [case])
    monkeypatch.setattr(runner_module, "load_backtest_corpus", lambda: [])

    working = _StaticJudgeClient(severity="high", confidence=0.9)
    failing = _AlwaysFailingJudgeClient()
    settings = Settings(_env_file=None, GEMINI_API_KEY="test")
    seen: list[JudgeModelResult] = []

    run_judge_model_probe(
        ("gemini-2.5-flash", "gemini-2.5-flash-lite"),
        settings_factory=lambda _model: settings,
        client_factory=lambda model: working if model == "gemini-2.5-flash" else failing,
        on_result=seen.append,
    )

    assert [r.model for r in seen] == ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    assert seen[0].failed is False
    assert seen[1].failed is True


def test_run_judge_model_probe_excludes_retry_wait_from_latency(monkeypatch):
    """(#257 bulgu 1 / #313) `client_factory` VERILMEDIGINDE (gercek `--run`
    yolu) `run_judge_model_probe` kendi `ResilientGeminiClient`'ini kurar ve
    `_LatencyTrackingJudge` bunun retry bekleme suresini NET gecikmeden
    ARINDIRIR. genai SDK'sini sahteleyip GERCEK bir retry tetikliyoruz.

    MUTASYON KANITI: `retry_client=retry_client` bagi kaldirilip `None`
    verilirse `avg_retry_wait_s` HER ZAMAN 0.0 kalir ve asagidaki
    `avg_retry_wait_s > 0.0` assert'i KIRILIR (elle dogrulandi — bkz. PR govdesi).
    """
    import ensemble.integrations.gemini.client as client_module
    import eval.eval_runner as runner_module

    case = next(c for c in load_conflict_corpus() if c.label == "conflict")
    monkeypatch.setattr(runner_module, "load_conflict_corpus", lambda: [case])
    monkeypatch.setattr(runner_module, "load_backtest_corpus", lambda: [])

    class _FakeApiError(Exception):
        def __init__(self, code: int):
            self.code = code
            super().__init__(f"api error {code}")

    class _FakeModels:
        def __init__(self) -> None:
            self.calls = 0

        def generate_content(self, model, contents, config=None):
            self.calls += 1
            if self.calls == 1:
                raise _FakeApiError(503)

            class _Resp:
                text = '{"severity":"high","confidence":0.9,"rationale":"x"}'

            return _Resp()

    class _FakeSdkClient:
        def __init__(self, models) -> None:
            self.models = models

    fake_models = _FakeModels()
    monkeypatch.setattr(client_module.genai_errors, "APIError", _FakeApiError, raising=False)
    monkeypatch.setattr(client_module.genai, "Client", lambda **kw: _FakeSdkClient(fake_models))

    settings = Settings(_env_file=None, GEMINI_API_KEY="k", GEMINI_MAX_RETRIES=5)

    results = run_judge_model_probe(("gemini-2.5-flash",), settings_factory=lambda _m: settings)

    assert len(results) == 1
    result = results[0]
    assert fake_models.calls == 2  # tek retry oldu
    assert result.failed is False
    assert result.avg_retry_wait_s > 0.0  # backoff GERCEKTEN olculdu, sifir degil
    # Net gecikme (gercek is neredeyse anlik) backoff'un cok altinda olmali —
    # ikisi karisiyor olsaydi avg_latency_s de retry bekleme kadar buyuk olurdu.
    assert result.avg_latency_s < result.avg_retry_wait_s


# ---------------------------------------------------------------------------
# Embedding boyutu probu
# ---------------------------------------------------------------------------


def test_run_embedding_dimension_probe_computes_margin():
    pairs = (
        EmbeddingPair(text_a="A", text_b="A2", related=True, note="test"),
        EmbeddingPair(text_a="A", text_b="B", related=False, note="test"),
    )
    vectors = {
        "A": [1.0, 0.0],
        "A2": [0.9, 0.1],  # A'ya yakin -> yuksek benzerlik (related)
        "B": [0.0, 1.0],  # A'ya dik -> dusuk benzerlik (unrelated)
    }
    client = _StaticEmbeddingClient(vectors)
    settings = Settings(_env_file=None, GEMINI_API_KEY="test")

    results = run_embedding_dimension_probe(
        (2,),
        settings_factory=lambda _dim: settings,
        client_factory=lambda _dim: client,
        pairs=pairs,
    )

    assert len(results) == 1
    result = results[0]
    assert result.dimensions == 2
    assert result.n_pairs == 2
    assert result.mean_related_sim > result.mean_unrelated_sim
    assert result.margin > 0
    assert result.failed is False
    assert result.storage_bytes == pgvector_storage_bytes(2)  # #257 bulgu 3 / #313
    # 2 essiz metin (A, B) + A2 = 3 essiz metin TEK batch cagrisinda gonderilir.
    assert client.calls == 1


def test_run_embedding_dimension_probe_raises_on_vector_count_mismatch():
    class _ShortClient:
        def embed_content(self, texts, *, task_type):
            return [[0.0, 0.0]]  # eksik vektor

    settings = Settings(_env_file=None, GEMINI_API_KEY="test")
    try:
        run_embedding_dimension_probe(
            (2,),
            settings_factory=lambda _dim: settings,
            client_factory=lambda _dim: _ShortClient(),
        )
        raise AssertionError("ValueError beklenirdi")
    except ValueError as exc:
        assert "vektor" in str(exc)


def test_run_embedding_dimension_probe_isolates_failing_dim():
    """(#257 bulgu 4 / #313) Bir boyutun Gemini cagrisi basarisiz olursa
    (`GeminiError` ailesi) o boyut `failed=True` ile isaretlenip devam
    edilir — ONCEKI boyutun ZATEN FATURALANMIS sonucu KAYBOLMAZ.
    `ValueError` (adapter sozlesme ihlali) ise KASITLI olarak burada
    yakalanmaz — bkz. `test_run_embedding_dimension_probe_raises_on_vector_count_mismatch`.
    """

    class _FailingEmbedClient:
        def embed_content(self, texts, *, task_type):
            raise GeminiTransientError("503 UNAVAILABLE (simulasyon)")

    pairs = (EmbeddingPair(text_a="A", text_b="B", related=False, note="test"),)
    working = _StaticEmbeddingClient({"A": [1.0, 0.0], "B": [0.0, 1.0]})
    failing = _FailingEmbedClient()
    settings = Settings(_env_file=None, GEMINI_API_KEY="test")

    results = run_embedding_dimension_probe(
        (768, 1536),
        settings_factory=lambda _dim: settings,
        client_factory=lambda dim: working if dim == 768 else failing,
        pairs=pairs,
    )

    by_dim = {r.dimensions: r for r in results}
    assert len(results) == 2  # her iki boyut da raporda VAR

    ok = by_dim[768]
    assert ok.failed is False
    assert ok.storage_bytes == pgvector_storage_bytes(768)

    bad = by_dim[1536]
    assert bad.failed is True
    assert bad.error is not None
    assert "503" in bad.error
    # depolama hesabi AGSIZ saf fonksiyon — basarisizlikta bile dolu.
    assert bad.storage_bytes == pgvector_storage_bytes(1536)


def test_run_embedding_dimension_probe_on_result_fires_per_dim(monkeypatch):
    class _FailingEmbedClient:
        def embed_content(self, texts, *, task_type):
            raise GeminiTransientError("simulasyon")

    pairs = (EmbeddingPair(text_a="A", text_b="B", related=False, note="test"),)
    working = _StaticEmbeddingClient({"A": [1.0, 0.0], "B": [0.0, 1.0]})
    failing = _FailingEmbedClient()
    settings = Settings(_env_file=None, GEMINI_API_KEY="test")
    seen: list[EmbeddingDimResult] = []

    run_embedding_dimension_probe(
        (768, 1536),
        settings_factory=lambda _dim: settings,
        client_factory=lambda dim: working if dim == 768 else failing,
        pairs=pairs,
        on_result=seen.append,
    )

    assert [r.dimensions for r in seen] == [768, 1536]
    assert seen[0].failed is False
    assert seen[1].failed is True


# ---------------------------------------------------------------------------
# CLI guvenlik yollari (maliyet kontrolu, #244)
# ---------------------------------------------------------------------------


def test_main_rejects_when_estimate_exceeds_max_calls(capsys):
    exit_code = main(["--max-calls", "1"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "REDDEDILDI" in captured.out


def test_main_prints_worst_case_and_storage_without_key(capsys):
    """(#257 bulgu 2 + 3 / #313) En-kotu-durum HTTP istegi VE embedding
    depolama/indeks boyutu — HER IKISI de GEMINI_API_KEY OLMADAN gorunur
    (agsiz tahmin yolunda), key gerekmez."""
    exit_code = main(["--embedding-dims", "768,1536,3072"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "EN KOTU DURUM" in captured.out
    assert "GEMINI_MAX_RETRIES=" in captured.out
    assert "768=3080bayt" in captured.out
    assert "1536=6152bayt" in captured.out
    assert "3072=12296bayt" in captured.out


def test_main_without_key_prints_message_and_returns_zero(monkeypatch, capsys):
    import eval.model_secimi_eval as mod

    monkeypatch.setattr(
        mod, "Settings", lambda *a, **kw: Settings(_env_file=None, GEMINI_API_KEY=None)
    )
    exit_code = mod.main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "GEMINI_API_KEY tanimli DEGIL" in captured.out


def test_main_with_key_but_without_run_flag_skips_real_calls(monkeypatch, capsys):
    import eval.model_secimi_eval as mod

    monkeypatch.setattr(
        mod, "Settings", lambda *a, **kw: Settings(_env_file=None, GEMINI_API_KEY="fake")
    )

    def _boom(*_args, **_kwargs):
        raise AssertionError("--run verilmeden gercek cagri denenmemeli")

    monkeypatch.setattr(mod, "run_judge_model_probe", _boom)
    monkeypatch.setattr(mod, "run_embedding_dimension_probe", _boom)

    exit_code = mod.main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--run VERILMEDI" in captured.out


def test_main_run_reports_failed_model_visibly_and_persists_incrementally(monkeypatch, capsys, tmp_path):
    """(#257 bulgu 1 + 4 / #313) UCTAN UCA kanit: sahte bir BASARISIZ
    saglayici ile `main(["--run"])` kosturulup raporda (hem stdout hem
    diske yazilan JSON'da) basarisizligin GERCEKTEN GORUNDUGU dogrulanir —
    "makul gorunen ama yanlis" bir satir UYDURULMADIGI VE onceki basarili
    modelin sonucunun KAYBOLMADIGI kanitlanir.
    """
    import eval.model_secimi_eval as mod

    monkeypatch.setattr(
        mod, "Settings", lambda *a, **kw: Settings(_env_file=None, GEMINI_API_KEY="fake")
    )
    results_path = tmp_path / "model-secimi-sonuclar.json"
    monkeypatch.setattr(mod, "_RESULTS_PATH", results_path)
    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)  # relative_to() icin tutarli taban

    def _fake_judge_probe(models, *, on_result=None, **_kw):
        ok = mod.JudgeModelResult(
            model=models[0],
            precision=0.9,
            recall=0.9,
            f05=0.9,
            f1=0.9,
            tp=1,
            total=1,
            real_calls=1,
            avg_latency_s=0.01,
        )
        bad = mod.JudgeModelResult(
            model=models[1],
            real_calls=3,
            error_count=1,
            failed=True,
            error="429 RESOURCE_EXHAUSTED (simulasyon)",
        )
        for r in (ok, bad):
            if on_result:
                on_result(r)
        return [ok, bad]

    def _fake_embedding_probe(dims, *, on_result=None, **_kw):
        r = mod.EmbeddingDimResult(
            dimensions=dims[0], storage_bytes=mod.pgvector_storage_bytes(dims[0])
        )
        if on_result:
            on_result(r)
        return [r]

    monkeypatch.setattr(mod, "run_judge_model_probe", _fake_judge_probe)
    monkeypatch.setattr(mod, "run_embedding_dimension_probe", _fake_embedding_probe)

    exit_code = mod.main(
        ["--run", "--judge-models", "model-a,model-b", "--embedding-dims", "768"]
    )
    captured = capsys.readouterr()

    # 1) Basarisiz model raporda GERCEKTEN goruyor — "makul" bir P/R/F0.5
    #    satiri UYDURULMUYOR, acikca BASARISIZ deniyor + ham hata mesaji var.
    assert "model-b: BASARISIZ" in captured.out
    assert "429 RESOURCE_EXHAUSTED" in captured.out
    # 2) Basarili modelin sonucu KAYBOLMADI (#257 bulgu 4 / #313).
    assert "model-a: precision=0.9000" in captured.out
    # 3) Kismi basarisizlik exit code'da da GORUNUR — sessizce 0 donmuyor.
    assert exit_code == 2

    persisted = json.loads(results_path.read_text(encoding="utf-8"))
    judge_by_model = {r["model"]: r for r in persisted["judge_models"]}
    assert judge_by_model["model-b"]["failed"] is True
    assert judge_by_model["model-a"]["failed"] is False
    assert len(persisted["embedding_dims"]) == 1
