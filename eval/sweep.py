"""Threshold sweep (#29) — Jaccard × similarity eşik ızgarası taraması.

Eval runner'ı farklı eşik kombinasyonlarıyla koşar, en iyi F1'i bulur.
Sonuçlar eval/sweep_results.json'a yazılır → #18 kalibrasyon kanıtı.

Kullanım:
    python -m eval.sweep                     # varsayılan ızgara
    python -m eval.sweep --fine              # ince ızgara
    python -m eval.sweep --exclude-same      # aynı-yazar hariç
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path

from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from eval.eval_runner import EvalReport, EvalRunner

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SWEEP_OUTPUT = _REPO_ROOT / "eval" / "sweep_results.json"


# ---------------------------------------------------------------------------
# Varsayılan ızgaralar
# ---------------------------------------------------------------------------

JACCARD_GRID_DEFAULT = [0.0, 0.05, 0.1, 0.15, 0.2]
SIMILARITY_GRID_DEFAULT = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]

JACCARD_GRID_FINE = [0.0, 0.02, 0.05, 0.08, 0.1, 0.12, 0.15, 0.18, 0.2, 0.25, 0.3]
SIMILARITY_GRID_FINE = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6]


# ---------------------------------------------------------------------------
# Veri yapıları
# ---------------------------------------------------------------------------

@dataclass
class SweepPoint:
    """Tek bir eşik kombinasyonunun sonucu."""
    min_jaccard: float
    min_similarity: float
    exclude_same_author: bool
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    tn: int
    total: int

    def to_dict(self) -> dict:
        return {
            "min_jaccard": self.min_jaccard,
            "min_similarity": self.min_similarity,
            "exclude_same_author": self.exclude_same_author,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "total": self.total,
        }


@dataclass
class SweepReport:
    """Tam sweep raporu."""
    points: list[SweepPoint]
    best: SweepPoint | None
    best_excluding_same: SweepPoint | None

    def to_dict(self) -> dict:
        return {
            "total_combinations": len(self.points),
            "best": self.best.to_dict() if self.best else None,
            "best_excluding_same_author": (
                self.best_excluding_same.to_dict()
                if self.best_excluding_same
                else None
            ),
            "grid": [p.to_dict() for p in self.points],
        }


# ---------------------------------------------------------------------------
# Sweep mantığı
# ---------------------------------------------------------------------------

def run_sweep(
    *,
    jaccard_grid: list[float] | None = None,
    similarity_grid: list[float] | None = None,
    include_same_author_axis: bool = True,
) -> SweepReport:
    """Eşik ızgarasını tarar ve SweepReport döner.

    Parametreler:
        jaccard_grid: Jaccard eşik değerleri listesi.
        similarity_grid: Similarity eşik değerleri listesi.
        include_same_author_axis: True ise her kombinasyon hem
            aynı-yazar dahil hem hariç koşulur.
    """
    jg = jaccard_grid or JACCARD_GRID_DEFAULT
    sg = similarity_grid or SIMILARITY_GRID_DEFAULT

    # Aynı-yazar eksenleri
    same_author_modes = [False]
    if include_same_author_axis:
        same_author_modes = [False, True]

    judge = FakeJudgeAdapter()
    points: list[SweepPoint] = []

    for min_j, min_s, exclude_same in product(jg, sg, same_author_modes):
        runner = EvalRunner(
            judge=judge,
            exclude_same_author=exclude_same,
            min_jaccard=min_j,
            min_similarity=min_s,
        )
        report: EvalReport = runner.run_eval(use_backtest=True, use_curated=True)

        points.append(SweepPoint(
            min_jaccard=min_j,
            min_similarity=min_s,
            exclude_same_author=exclude_same,
            precision=report.overall.precision,
            recall=report.overall.recall,
            f1=report.overall.f1,
            tp=report.overall.tp,
            fp=report.overall.fp,
            fn=report.overall.fn,
            tn=report.overall.tn,
            total=report.overall.total,
        ))

    # En iyi F1'i bul (aynı-yazar dahil)
    all_include = [p for p in points if not p.exclude_same_author]
    best = max(all_include, key=lambda p: (p.f1, p.precision, -p.fp)) if all_include else None

    # En iyi F1 (aynı-yazar hariç)
    all_exclude = [p for p in points if p.exclude_same_author]
    best_excl = max(all_exclude, key=lambda p: (p.f1, p.precision, -p.fp)) if all_exclude else None

    return SweepReport(points=points, best=best, best_excluding_same=best_excl)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    fine = "--fine" in sys.argv

    jg = JACCARD_GRID_FINE if fine else JACCARD_GRID_DEFAULT
    sg = SIMILARITY_GRID_FINE if fine else SIMILARITY_GRID_DEFAULT

    print(f"Sweep başlıyor: {len(jg)} Jaccard × {len(sg)} similarity × 2 aynı-yazar = "
          f"{len(jg) * len(sg) * 2} kombinasyon")

    report = run_sweep(
        jaccard_grid=jg,
        similarity_grid=sg,
        include_same_author_axis=True,
    )

    # Sonuçları dosyaya yaz
    _SWEEP_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _SWEEP_OUTPUT.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nSonuçlar: {_SWEEP_OUTPUT.relative_to(_REPO_ROOT)}")
    print(f"Toplam kombinasyon: {len(report.points)}")

    if report.best:
        b = report.best
        print(f"\n{'='*60}")
        print(f"  EN IYI (aynı-yazar DAHIL):")
        print(f"    Jaccard >= {b.min_jaccard}  |  Similarity >= {b.min_similarity}")
        print(f"    F1={b.f1:.4f}  P={b.precision:.4f}  R={b.recall:.4f}")
        print(f"    TP={b.tp}  FP={b.fp}  FN={b.fn}  TN={b.tn}")
        print(f"{'='*60}")

    if report.best_excluding_same:
        b = report.best_excluding_same
        print(f"\n  EN IYI (aynı-yazar HARIÇ):")
        print(f"    Jaccard >= {b.min_jaccard}  |  Similarity >= {b.min_similarity}")
        print(f"    F1={b.f1:.4f}  P={b.precision:.4f}  R={b.recall:.4f}")
        print(f"    TP={b.tp}  FP={b.fp}  FN={b.fn}  TN={b.tn}")

    # Önerilen config değerleri
    if report.best:
        b = report.best
        print(f"\n  Önerilen config (config.py / .env):")
        print(f"    RADAR_MIN_JACCARD={b.min_jaccard}")
        print(f"    RADAR_MIN_SIMILARITY={b.min_similarity}")

    print()


if __name__ == "__main__":
    main()
