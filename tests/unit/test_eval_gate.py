"""Eval precision-gate (#30) testleri."""

from eval.eval_runner import EvalReport, EvalResult
from eval.gate import MIN_F05, MIN_PRECISION, evaluate_gate, run_gate


def _report(
    precision: float,
    f05: float,
    *,
    total: int = 118,
    backtest_total: int = 106,
) -> EvalReport:
    report = EvalReport()
    report.overall = EvalResult(precision=precision, f05=f05, total=total)
    report.backtest = EvalResult(total=backtest_total)
    return report


def test_gate_passes_at_calibrated_point():
    """#162 sonrası kalibre nokta (P=1.0, F0.5=0.8929) tabanları geçer."""
    assert evaluate_gate(_report(1.0, 0.8929)) == []


def test_gate_fails_on_precision_regression():
    """Tek FP bile precision'ı 6/7=0.857'ye düşürür → taban 0.90 yakalar."""
    violations = evaluate_gate(_report(0.857, 0.90))
    assert any("precision" in v for v in violations)


def test_gate_fails_on_f05_regression():
    """F0.5 tabanın altına düşerse (precision yüksek olsa da) yakalanır."""
    violations = evaluate_gate(_report(0.95, 0.50))
    assert any("F0.5" in v for v in violations)


def test_gate_boundary_is_inclusive():
    """Tam tabanda (>=) geçer; hemen altında kırılır."""
    assert evaluate_gate(_report(MIN_PRECISION, MIN_F05)) == []
    assert evaluate_gate(_report(MIN_PRECISION - 0.001, MIN_F05)) != []
    assert evaluate_gate(_report(MIN_PRECISION, MIN_F05 - 0.001)) != []


def test_gate_fails_on_missing_backtest():
    """Backtest dataset kaybolursa (curated-only) fail-closed — maskeleme yok."""
    violations = evaluate_gate(_report(1.0, 1.0, total=12, backtest_total=0))
    assert any("backtest" in v for v in violations)


def test_gate_fails_on_shrunk_corpus():
    """Toplam vaka beklenenden küçükse gate kırılır (sessiz daralma koruması)."""
    violations = evaluate_gate(_report(1.0, 0.9375, total=40, backtest_total=30))
    assert any("toplam" in v for v in violations)


def test_gate_catches_next_tp_loss():
    """Sonraki tespit kaybı: TP 5->4, F0.5=0.8333 < 0.89 → yakalanır."""
    violations = evaluate_gate(_report(1.0, 0.8333))
    assert any("F0.5" in v for v in violations)


def test_real_corpus_passes_gate():
    """Gerçek korpus kalibre operasyon noktasında kapıyı geçmeli.

    Bu, #30'un asıl işi: bu test kırmızıysa dedektör/judge regresyona
    girmiş demektir (CI de aynı `make eval-gate` ile kırmızı olur).
    """
    report = run_gate()
    assert evaluate_gate(report) == [], (
        f"Kapı kırıldı: precision={report.overall.precision} "
        f"F0.5={report.overall.f05} FP={report.overall.fp}"
    )
