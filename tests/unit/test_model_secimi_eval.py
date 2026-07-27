"""YZ model secimi olcum harness'i (#244) testleri.

Gercek Gemini cagrisi YAPMAZ — `_StaticJudgeClient`/`_StaticEmbeddingClient`
enjekte edilir (bkz. `tests/unit/test_provider_eval.py`'daki ayni desen:
`GeminiJudgeAdapter`/`GeminiEmbeddingsAdapter` `client=None` degilse kendi
`ResilientGeminiClient`'ini hic kurmaz — GEMINI_API_KEY gerekmez).
"""

from ensemble.config import Settings
from eval.model_secimi_eval import (
    DEFAULT_EMBEDDING_DIMS,
    DEFAULT_JUDGE_MODELS,
    EMBEDDING_SAMPLE,
    EmbeddingPair,
    _unique_sample_texts,
    estimate_real_judge_calls,
    estimate_total_calls,
    main,
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


# ---------------------------------------------------------------------------
# CLI guvenlik yollari (maliyet kontrolu, #244)
# ---------------------------------------------------------------------------


def test_main_rejects_when_estimate_exceeds_max_calls(capsys):
    exit_code = main(["--max-calls", "1"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "REDDEDILDI" in captured.out


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
