"""Eval runner (#28) — kuratörlü (#26) + backtest (#27) corpus'larını koşar,
dataset-bazlı kırılım ve per-case detaylar raporlar.

Kullanım:
    python -m eval.eval_runner                    # tüm corpus, tüm modlar
    python -m eval.eval_runner --curated-only     # yalnız kuratörlü
    python -m eval.eval_runner --exclude-same     # aynı-yazar çiftleri hariç

Kontrat: docs/sprint2-kontratlar.md Ek C.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ensemble.engine.radar import file_overlap_candidates, passes_similarity_threshold
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.models import Detection
from ensemble.ports import JudgePort
from tests.fixtures.conflict_corpus import ConflictCase, load_conflict_corpus

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKTEST_DATASET = _REPO_ROOT / "eval" / "datasets" / "backtest-grup54.jsonl"

_SAME_AUTHOR_TAG = "[ayni-yazar]"


# ---------------------------------------------------------------------------
# Veri yapıları
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    """Tek bir vakanın eval sonucu — debug ve kalibrasyon için."""

    case_id: str
    dataset: Literal["curated", "backtest"]
    label: Literal["conflict", "no_conflict"]
    predicted: Literal["conflict", "no_conflict"]
    outcome: Literal["tp", "fp", "fn", "tn"]
    same_author: bool
    severity: str
    confidence: float


@dataclass
class EvalResult:
    """Precision / recall / F1 / F0.5 metrikleri + ham sayılar.

    F0.5 = precision-ağırlıklı Fβ (β=0.5) — FP #1 risk olduğu için
    operasyon noktası seçiminde birincil metrik (issue #28/#18).
    """

    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    f05: float = 0.0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    total: int = 0

    def to_dict(self) -> dict:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "f05": self.f05,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "total": self.total,
        }


@dataclass
class EvalReport:
    """Tam eval raporu: kırılımlar + per-case detaylar."""

    overall: EvalResult = field(default_factory=EvalResult)
    curated: EvalResult = field(default_factory=EvalResult)
    backtest: EvalResult = field(default_factory=EvalResult)
    cases: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall": self.overall.to_dict(),
            "curated": self.curated.to_dict(),
            "backtest": self.backtest.to_dict(),
            "cases": [
                {
                    "case_id": c.case_id,
                    "dataset": c.dataset,
                    "label": c.label,
                    "predicted": c.predicted,
                    "outcome": c.outcome,
                    "same_author": c.same_author,
                    "severity": c.severity,
                    "confidence": c.confidence,
                }
                for c in self.cases
            ],
        }


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _compute_metrics(tp: int, fp: int, fn: int, tn: int) -> EvalResult:
    total = tp + fp + fn + tn
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    # Fβ (β=0.5): precision'ı 4x ağırlıklandırır — FP = #1 risk (bkz.
    # docs/eval-metodoloji-devir.md §1). Payda yalnız P=R=0'da sıfırlanır.
    f05 = (
        1.25 * (precision * recall) / (0.25 * precision + recall)
        if (0.25 * precision + recall) > 0
        else 0.0
    )
    return EvalResult(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        f05=round(f05, 4),
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        total=total,
    )


def _is_same_author(case: ConflictCase) -> bool:
    """Aynı-yazar çifti mi? Not alanındaki etikete VEYA actor karşılaştırmasına bakar."""
    if case.event_a.actor == case.event_b.actor:
        return True
    if _SAME_AUTHOR_TAG in case.note:
        return True
    return False


# ---------------------------------------------------------------------------
# Dataset yükleyiciler
# ---------------------------------------------------------------------------


def load_backtest_corpus() -> list[ConflictCase]:
    """Backtest dataset'ini yükler (sim=None — dedektör hesaplar)."""
    if not _BACKTEST_DATASET.exists():
        return []
    lines = _BACKTEST_DATASET.read_text(encoding="utf-8").splitlines()
    return [ConflictCase.model_validate(json.loads(line)) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# EvalRunner
# ---------------------------------------------------------------------------


class EvalRunner:
    """Eval corpus'larını koşar ve metrikleri hesaplar.

    Parametreler:
        judge: JudgePort — gerçek veya fake adapter.
        exclude_same_author: True ise [ayni-yazar] çiftleri eval'den çıkarılır
            (ürün semantiği: radar farklı kişileri uyarır).
        min_jaccard: Eşik parametresi — file_overlap aşamasında uygulanır.
            None ise eşik uygulanmaz (tüm çiftler değerlendirilir).
        min_similarity: Eşik parametresi — similarity filtrelemesi.
            None ise filtre uygulanmaz.
    """

    def __init__(
        self,
        judge: JudgePort,
        *,
        exclude_same_author: bool = False,
        min_jaccard: float | None = None,
        min_similarity: float | None = None,
    ) -> None:
        self.judge = judge
        self.exclude_same_author = exclude_same_author
        self.min_jaccard = min_jaccard
        self.min_similarity = min_similarity

    def _should_skip(self, case: ConflictCase) -> bool:
        """Aynı-yazar filtresini uygular."""
        if self.exclude_same_author and _is_same_author(case):
            return True
        return False

    def _apply_thresholds(self, case: ConflictCase) -> bool:
        """Radar aday/eşik yolunu uygular — geçemezse False (skip)."""
        candidates = file_overlap_candidates(
            [case.event_a, case.event_b],
            min_jaccard=self.min_jaccard or 0.0,
            exclude_same_actor=self.exclude_same_author,
        )
        if not candidates:
            return False

        return passes_similarity_threshold(case.sim, self.min_similarity or 0.0)

    def _evaluate_case(
        self, case: ConflictCase, dataset_tag: Literal["curated", "backtest"]
    ) -> CaseResult:
        """Tek bir vakayı değerlendirir."""
        detection: Detection = self.judge.judge_conflict(
            case.event_a,
            case.event_b,
            case.overlap,
            case.sim,
        )

        # Karar: med/high = conflict, low = no_conflict
        predicted_conflict = detection.severity in ("med", "high")
        predicted = "conflict" if predicted_conflict else "no_conflict"
        actual_conflict = case.label == "conflict"

        if predicted_conflict and actual_conflict:
            outcome = "tp"
        elif predicted_conflict and not actual_conflict:
            outcome = "fp"
        elif not predicted_conflict and actual_conflict:
            outcome = "fn"
        else:
            outcome = "tn"

        return CaseResult(
            case_id=case.case_id,
            dataset=dataset_tag,
            label=case.label,
            predicted=predicted,
            outcome=outcome,
            same_author=_is_same_author(case),
            severity=detection.severity,
            confidence=detection.confidence,
        )

    def run_eval(
        self,
        *,
        use_backtest: bool = True,
        use_curated: bool = True,
    ) -> EvalReport:
        """Eval'i koşar ve detaylı rapor döner.

        Parametreler:
            use_backtest: False ise backtest corpus'u atlanır.
            use_curated: False ise kuratörlü corpus atlanır.
        """
        curated_cases = load_conflict_corpus() if use_curated else []
        backtest_cases = load_backtest_corpus() if use_backtest else []

        all_results: list[CaseResult] = []

        # Kuratörlü vakaları koş
        for case in curated_cases:
            if self._should_skip(case):
                continue
            if not self._apply_thresholds(case):
                # Eşik geçilemezse, vakayı "no_conflict" tahmin olarak say
                all_results.append(
                    CaseResult(
                        case_id=case.case_id,
                        dataset="curated",
                        label=case.label,
                        predicted="no_conflict",
                        outcome="tn" if case.label == "no_conflict" else "fn",
                        same_author=_is_same_author(case),
                        severity="low",
                        confidence=0.0,
                    )
                )
                continue
            all_results.append(self._evaluate_case(case, "curated"))

        # Backtest vakalarını koş
        for case in backtest_cases:
            if self._should_skip(case):
                continue
            if not self._apply_thresholds(case):
                all_results.append(
                    CaseResult(
                        case_id=case.case_id,
                        dataset="backtest",
                        label=case.label,
                        predicted="no_conflict",
                        outcome="tn" if case.label == "no_conflict" else "fn",
                        same_author=_is_same_author(case),
                        severity="low",
                        confidence=0.0,
                    )
                )
                continue
            all_results.append(self._evaluate_case(case, "backtest"))

        # Metrikleri hesapla
        report = EvalReport(cases=all_results)

        # Genel
        report.overall = _compute_metrics(
            tp=sum(1 for r in all_results if r.outcome == "tp"),
            fp=sum(1 for r in all_results if r.outcome == "fp"),
            fn=sum(1 for r in all_results if r.outcome == "fn"),
            tn=sum(1 for r in all_results if r.outcome == "tn"),
        )

        # Kuratörlü kırılım
        curated_results = [r for r in all_results if r.dataset == "curated"]
        report.curated = _compute_metrics(
            tp=sum(1 for r in curated_results if r.outcome == "tp"),
            fp=sum(1 for r in curated_results if r.outcome == "fp"),
            fn=sum(1 for r in curated_results if r.outcome == "fn"),
            tn=sum(1 for r in curated_results if r.outcome == "tn"),
        )

        # Backtest kırılım
        backtest_results = [r for r in all_results if r.dataset == "backtest"]
        report.backtest = _compute_metrics(
            tp=sum(1 for r in backtest_results if r.outcome == "tp"),
            fp=sum(1 for r in backtest_results if r.outcome == "fp"),
            fn=sum(1 for r in backtest_results if r.outcome == "fn"),
            tn=sum(1 for r in backtest_results if r.outcome == "tn"),
        )

        return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_metrics(name: str, result: EvalResult) -> None:
    print(f"\n  {name}:")
    print(f"    Precision : {result.precision:.4f}")
    print(f"    Recall    : {result.recall:.4f}")
    print(f"    F1        : {result.f1:.4f}")
    print(f"    F0.5      : {result.f05:.4f}")
    print(
        f"    TP={result.tp}  FP={result.fp}  FN={result.fn}  TN={result.tn}  (toplam={result.total})"
    )


def main() -> None:
    exclude_same = "--exclude-same" in sys.argv
    curated_only = "--curated-only" in sys.argv
    backtest_only = "--backtest-only" in sys.argv

    judge = FakeJudgeAdapter()
    runner = EvalRunner(judge=judge, exclude_same_author=exclude_same)

    report = runner.run_eval(
        use_backtest=not curated_only,
        use_curated=not backtest_only,
    )

    print("=" * 60)
    print("  Eval Runner (#28) — Sonuçlar")
    print("=" * 60)
    if exclude_same:
        print("  [!] Aynı-yazar çiftleri HARİÇ tutuldu")

    _print_metrics("GENEL", report.overall)
    if not backtest_only:
        _print_metrics("Kuratörlü (#26)", report.curated)
    if not curated_only:
        _print_metrics("Backtest (#27)", report.backtest)

    # Yanlış sınıflamalar (debug)
    errors = [c for c in report.cases if c.outcome in ("fp", "fn")]
    if errors:
        print(f"\n  Hatalar ({len(errors)}):")
        for e in errors:
            tag = " [ayni-yazar]" if e.same_author else ""
            print(
                f"    {e.outcome.upper()} {e.case_id}: "
                f"label={e.label}, predicted={e.predicted}, "
                f"severity={e.severity}, conf={e.confidence:.2f}{tag}"
            )

    print()


if __name__ == "__main__":
    main()
