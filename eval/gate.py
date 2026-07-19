"""Eval precision-gate (#30) — CI regresyon kapısı.

Eval'i kalibre operasyon noktasında (eşiksiz = RADAR_MIN_JACCARD/SIMILARITY=0.0,
bkz. `eval/kalibrasyon-raporu.md`) koşar; precision veya F0.5 kalibre tabanın
altına düşerse exit 1 ile CI'ı kırar. Dedektör + kural-tabanlı judge (FakeJudge)
regresyonuna karşı koruma — gerçek Gemini judge yolu bu kapının DIŞINDA
(bkz. kalibrasyon-raporu.md §4; canlı yol için #58/spot-check).

Ayrıca korpus bütünlüğü denetlenir: backtest dataset'i yüklenemez ya da toplam
vaka daralırsa gate fail-closed olur (curated-only'ye düşüp regresyonu maskelemez).

Kaynak: #30 (ön-koşul #28 ✓). Kalibrasyon kanıtı: #18.
Offline/deterministik — FakeJudgeAdapter kullanır, ağ/anahtar gerektirmez.

Kullanım:
    python -m eval.gate      # kapı — düşükse exit 1
    make eval-gate
"""

from __future__ import annotations

import sys

from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from eval.eval_runner import EvalReport, EvalRunner

# Kalibre tabanlar. #18 operasyon noktası: precision=1.0, F0.5=0.9375, total=118.
# - precision 0.90: FP #1 risk; TP=6/FP=0'da tek FP bile P'yi 6/7=0.857'ye düşürür.
# - F0.5 0.90: recall regresyonu da yakalanır — tek tespit kaybı (TP 6->5) F0.5'i
#   0.893'e indirir (<0.90). 0.85 tabanı bunu KAÇIRIYORDU (adversarial bulgu).
# - MIN_TOTAL: korpus daralması/kaybı maskelemesin (fail-closed).
MIN_PRECISION = 0.90
MIN_F05 = 0.90
MIN_TOTAL = 100


def evaluate_gate(
    report: EvalReport,
    *,
    min_precision: float = MIN_PRECISION,
    min_f05: float = MIN_F05,
    min_total: int = MIN_TOTAL,
) -> list[str]:
    """Tabanları geçemeyen ihlalleri döner (boş liste = geçti).

    Metrik tabanlarına ek olarak KORPUS BÜTÜNLÜĞÜ denetlenir: backtest dataset'i
    yüklenemez (backtest.total==0) ya da toplam vaka daralırsa gate fail-closed
    olur — aksi halde curated-only P=1.0'a düşüp regresyonu maskeleyebilir.
    Sınır dahil: metrik tam tabana eşitse geçer (`<` karşılaştırması).
    """
    overall = report.overall
    violations: list[str] = []
    if overall.total < min_total:
        violations.append(
            f"toplam vaka {overall.total} < {min_total} (korpus daralmış/kaybolmuş?)"
        )
    if report.backtest.total == 0:
        violations.append(
            "backtest korpusu boş/yüklenemedi (eval/datasets/backtest-grup54.jsonl)"
        )
    if overall.precision < min_precision:
        violations.append(
            f"precision {overall.precision:.4f} < taban {min_precision:.2f}"
        )
    if overall.f05 < min_f05:
        violations.append(f"F0.5 {overall.f05:.4f} < taban {min_f05:.2f}")
    return violations


def run_gate() -> EvalReport:
    """Eval'i kalibre operasyon noktasında (eşiksiz, aynı-yazar dahil) koşar."""
    runner = EvalRunner(judge=FakeJudgeAdapter())
    return runner.run_eval(use_backtest=True, use_curated=True)


def main() -> None:
    report = run_gate()
    o = report.overall
    violations = evaluate_gate(report)

    print("=" * 60)
    print("  Eval precision-gate (#30)")
    print("=" * 60)
    print(f"  Precision : {o.precision:.4f}  (taban {MIN_PRECISION:.2f})")
    print(f"  F0.5      : {o.f05:.4f}  (taban {MIN_F05:.2f})")
    print(f"  TP={o.tp} FP={o.fp} FN={o.fn} TN={o.tn}")
    print(f"  Korpus    : toplam={o.total} (taban {MIN_TOTAL})  backtest={report.backtest.total}")

    if not violations:
        print("\n  GECTI — metrikler kalibre tabanin ustunde.")
        return

    print("\n  KIRILDI:")
    for violation in violations:
        print(f"    - {violation}")
    print(
        "\n  Dedektor/judge regresyonu olabilir; "
        "eval/kalibrasyon-raporu.md'yi gozden gecir."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
