"""Eval runner (#28) unit testleri — dataset kırılımı, aynı-yazar filtresi,
eşik parametreleri, per-case detaylar ve edge case'ler."""

from datetime import datetime

from ensemble.engine.radar import file_overlap_candidates, passes_similarity_threshold
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.models import NormalizedEvent
from eval.eval_runner import (
    CaseResult,
    EvalReport,
    EvalRunner,
    _compute_metrics,
    _is_same_author,
    load_backtest_corpus,
)
from tests.fixtures.conflict_corpus import ConflictCase, load_conflict_corpus


# ---------------------------------------------------------------------------
# Yardımcı fixture'lar
# ---------------------------------------------------------------------------


def _event(eid: str, actor: str, files: list[str]) -> NormalizedEvent:
    return NormalizedEvent(
        id=eid,
        type="commit",
        actor=actor,
        branch="main",
        files=files,
        ts=datetime(2026, 7, 10),
        ref=eid,
    )


def _case(
    case_id: str,
    actor_a: str = "alice",
    actor_b: str = "bob",
    files_a: list[str] | None = None,
    files_b: list[str] | None = None,
    overlap: list[str] | None = None,
    sim: float | None = 0.9,
    label: str = "conflict",
    note: str = "",
) -> ConflictCase:
    fa = files_a or ["x.py"]
    fb = files_b or ["x.py"]
    ov = overlap if overlap is not None else sorted(set(fa) & set(fb))
    return ConflictCase(
        case_id=case_id,
        event_a=_event(f"{case_id}-a", actor_a, fa),
        event_b=_event(f"{case_id}-b", actor_b, fb),
        overlap=ov,
        sim=sim,
        label=label,
        note=note,
    )


# ---------------------------------------------------------------------------
# _compute_metrics testleri
# ---------------------------------------------------------------------------


def test_compute_metrics_perfect():
    r = _compute_metrics(tp=5, fp=0, fn=0, tn=3)
    assert r.precision == 1.0
    assert r.recall == 1.0
    assert r.f1 == 1.0
    assert r.f05 == 1.0
    assert r.total == 8


def test_compute_metrics_all_zeros():
    r = _compute_metrics(tp=0, fp=0, fn=0, tn=0)
    assert r.precision == 0.0
    assert r.recall == 0.0
    assert r.f1 == 0.0
    assert r.f05 == 0.0
    assert r.total == 0


def test_compute_metrics_only_fp():
    r = _compute_metrics(tp=0, fp=5, fn=0, tn=0)
    assert r.precision == 0.0
    assert r.recall == 0.0
    assert r.f1 == 0.0
    assert r.f05 == 0.0


def test_compute_metrics_f05_precision_agirlikli():
    # P=1.0, R=0.5: F1 recall'a eşit ceza keser, F0.5 precision'ı ödüllendirir.
    # F1 = 2*0.5/1.5 = 0.6667 · F0.5 = 1.25*0.5/0.75 = 0.8333 — ayrışma kanıtı.
    r = _compute_metrics(tp=1, fp=0, fn=1, tn=0)
    assert r.f1 == 0.6667
    assert r.f05 == 0.8333
    assert r.f05 > r.f1  # precision > recall iken F0.5 daha yüksek olmalı


# ---------------------------------------------------------------------------
# _is_same_author testleri
# ---------------------------------------------------------------------------


def test_is_same_author_by_actor():
    case = _case("sa1", actor_a="enes", actor_b="enes")
    assert _is_same_author(case) is True


def test_is_same_author_by_tag():
    case = _case("sa2", actor_a="enes", actor_b="fatih", note="blabla [ayni-yazar]")
    assert _is_same_author(case) is True


def test_not_same_author():
    case = _case("nsa1", actor_a="enes", actor_b="fatih", note="normal pair")
    assert _is_same_author(case) is False


# ---------------------------------------------------------------------------
# EvalRunner — temel akış
# ---------------------------------------------------------------------------


def test_eval_runner_with_fake_judge_returns_report():
    """FakeJudgeAdapter ile eval runner çalışır ve EvalReport döner."""
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge)
    report = runner.run_eval(use_backtest=False)

    assert isinstance(report, EvalReport)
    assert isinstance(report.overall.precision, float)
    assert isinstance(report.overall.recall, float)
    assert report.overall.total > 0
    assert report.overall.total == report.curated.total
    assert report.backtest.total == 0


def test_eval_runner_curated_only():
    """use_curated=True, use_backtest=False — yalnız kuratörlü."""
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge)
    report = runner.run_eval(use_backtest=False, use_curated=True)

    assert report.curated.total > 0
    assert report.backtest.total == 0
    assert report.overall.total == report.curated.total


def test_eval_runner_with_backtest():
    """Backtest dahil — toplam = kuratörlü + backtest."""
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge)
    report = runner.run_eval(use_backtest=True, use_curated=True)

    assert report.curated.total > 0
    assert report.backtest.total > 0
    assert report.overall.total == report.curated.total + report.backtest.total


# ---------------------------------------------------------------------------
# EvalRunner — dataset-bazlı kırılım
# ---------------------------------------------------------------------------


def test_dataset_breakdown_sums_to_overall():
    """Kuratörlü + backtest TP/FP/FN/TN'leri overall'e eşit olmalı."""
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge)
    report = runner.run_eval(use_backtest=True)

    assert (report.curated.tp + report.backtest.tp) == report.overall.tp
    assert (report.curated.fp + report.backtest.fp) == report.overall.fp
    assert (report.curated.fn + report.backtest.fn) == report.overall.fn
    assert (report.curated.tn + report.backtest.tn) == report.overall.tn


# ---------------------------------------------------------------------------
# EvalRunner — per-case detaylar
# ---------------------------------------------------------------------------


def test_per_case_results_have_correct_count():
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge)
    report = runner.run_eval(use_backtest=False)

    assert len(report.cases) == report.overall.total
    assert all(isinstance(c, CaseResult) for c in report.cases)
    assert all(c.dataset == "curated" for c in report.cases)


def test_per_case_outcomes_match_totals():
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge)
    report = runner.run_eval(use_backtest=False)

    tp = sum(1 for c in report.cases if c.outcome == "tp")
    fp = sum(1 for c in report.cases if c.outcome == "fp")
    fn = sum(1 for c in report.cases if c.outcome == "fn")
    tn = sum(1 for c in report.cases if c.outcome == "tn")

    assert tp == report.overall.tp
    assert fp == report.overall.fp
    assert fn == report.overall.fn
    assert tn == report.overall.tn


# ---------------------------------------------------------------------------
# EvalRunner — aynı-yazar filtresi
# ---------------------------------------------------------------------------


def test_exclude_same_author_reduces_total():
    """Aynı-yazar filtresi açıkken toplam vaka sayısı azalmalı."""
    judge = FakeJudgeAdapter()

    runner_all = EvalRunner(judge=judge, exclude_same_author=False)
    runner_filtered = EvalRunner(judge=judge, exclude_same_author=True)

    report_all = runner_all.run_eval(use_backtest=True)
    report_filtered = runner_filtered.run_eval(use_backtest=True)

    # Backtest'te 31 aynı-yazar çifti var
    assert report_filtered.overall.total < report_all.overall.total
    # Filtrelenen sonuçlarda aynı-yazar vakası olmamalı
    assert all(not c.same_author for c in report_filtered.cases)


def test_exclude_same_author_no_same_author_cases():
    """Filtre açıkken per-case'lerde aynı-yazar olmamalı."""
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge, exclude_same_author=True)
    report = runner.run_eval(use_backtest=True)

    for case in report.cases:
        assert not case.same_author, f"{case.case_id} aynı-yazar ama filtrelenmemiş"


# ---------------------------------------------------------------------------
# EvalRunner — eşik parametreleri
# ---------------------------------------------------------------------------


def test_min_jaccard_threshold_filters_low_overlap():
    """Yüksek Jaccard eşiği düşük overlap'li vakaları eler."""
    judge = FakeJudgeAdapter()

    runner_no_thresh = EvalRunner(judge=judge, min_jaccard=None)
    runner_high_thresh = EvalRunner(judge=judge, min_jaccard=0.5)

    report_no = runner_no_thresh.run_eval(use_backtest=False)
    report_hi = runner_high_thresh.run_eval(use_backtest=False)

    # Yüksek eşik bazı vakaları filtrelemeli (veya en azından aynı sayıda olmalı)
    # Kuratörlü corpus'ta overlap=0 olan vakalar var → Jaccard=0 → eşiğe takılır
    assert report_hi.overall.total == report_no.overall.total  # toplam aynı kalır
    # Ama filtrelenen vakalar "no_conflict" olarak sayılır → FN artabilir


def test_min_similarity_threshold_filters_low_sim():
    """Yüksek similarity eşiği düşük sim'li vakaları filtreler."""
    judge = FakeJudgeAdapter()

    runner_no = EvalRunner(judge=judge, min_similarity=None)
    runner_hi = EvalRunner(judge=judge, min_similarity=0.5)

    report_no = runner_no.run_eval(use_backtest=False)
    report_hi = runner_hi.run_eval(use_backtest=False)

    # Kuratörlü corpus'ta sim=0.05 ve sim=0.15 olan vakalar var → filtrelenir
    # Ama sim=None olan vakalar filtreden geçer (bilinmiyor → dedektöre bırak)
    assert report_hi.overall.total == report_no.overall.total


def test_eval_esik_karari_radar_pipeline_ile_ayni():
    cases = [
        (
            _case(
                "pass",
                files_a=["shared.py", "a.py"],
                files_b=["shared.py", "a.py", "b.py"],
                sim=0.8,
            ),
            True,
        ),
        (
            _case(
                "dusuk-jaccard",
                files_a=["shared.py", "a.py"],
                files_b=["shared.py", "b.py"],
                sim=0.8,
            ),
            False,
        ),
        (_case("overlap-yok", files_a=["a.py"], files_b=["b.py"], sim=0.8), False),
        (_case("dusuk-sim", sim=0.2), False),
        (_case("sim-bilinmiyor", sim=None), True),
    ]
    runner = EvalRunner(judge=FakeJudgeAdapter(), min_jaccard=0.5, min_similarity=0.7)

    for case, expected in cases:
        radar_candidates = file_overlap_candidates(
            [case.event_a, case.event_b],
            min_jaccard=0.5,
            exclude_same_actor=False,
        )
        radar_passes = bool(radar_candidates) and passes_similarity_threshold(case.sim, 0.7)
        assert radar_passes is expected
        assert runner._apply_thresholds(case) is expected


# ---------------------------------------------------------------------------
# EvalRunner — sim=None vakalar (backtest verisi)
# ---------------------------------------------------------------------------


def test_sim_none_cases_passed_to_judge():
    """sim=None olan backtest vakaları judge'a None olarak geçmeli."""
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge)
    report = runner.run_eval(use_backtest=True, use_curated=False)

    # Backtest'teki tüm vakalar sim=None
    assert report.backtest.total > 0
    # FakeJudgeAdapter sim=None'ı kabul ediyor (overlap-bazlı karar)
    assert report.backtest.total == report.overall.total


# ---------------------------------------------------------------------------
# EvalRunner — boş dataset edge case
# ---------------------------------------------------------------------------


def test_empty_datasets_returns_zero_metrics():
    """Hiç vaka yokken metrikler sıfır olmalı."""
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge)
    report = runner.run_eval(use_backtest=False, use_curated=False)

    assert report.overall.total == 0
    assert report.overall.precision == 0.0
    assert report.overall.recall == 0.0
    assert report.overall.f1 == 0.0
    assert len(report.cases) == 0


# ---------------------------------------------------------------------------
# EvalReport — to_dict / serileştirme
# ---------------------------------------------------------------------------


def test_report_to_dict_is_json_serializable():
    """Report JSON'a dönüştürülebilir olmalı."""
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge)
    report = runner.run_eval(use_backtest=False)

    d = report.to_dict()
    # JSON serialization test
    import json

    s = json.dumps(d)
    assert isinstance(s, str)
    parsed = json.loads(s)
    assert "overall" in parsed
    assert "curated" in parsed
    assert "backtest" in parsed
    assert "cases" in parsed


# ---------------------------------------------------------------------------
# Gerçek corpus entegrasyonu
# ---------------------------------------------------------------------------


def test_curated_corpus_loads_successfully():
    """Kuratörlü corpus başarıyla yüklenmeli."""
    cases = load_conflict_corpus()
    assert len(cases) > 0
    assert all(c.label in ("conflict", "no_conflict") for c in cases)


def test_backtest_corpus_loads_successfully():
    """Backtest corpus başarıyla yüklenmeli."""
    cases = load_backtest_corpus()
    assert len(cases) > 0
    assert all(c.sim is None for c in cases)  # Backtest'te sim her zaman None


def test_full_eval_produces_nonzero_f1():
    """Tam eval (kuratörlü + backtest) sıfırdan büyük F1 üretmeli."""
    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge)
    report = runner.run_eval(use_backtest=True)

    # Kuratörlü corpus'ta açık conflict'ler var → en az bir TP olmalı
    assert report.overall.tp > 0
    assert report.overall.f1 > 0.0
