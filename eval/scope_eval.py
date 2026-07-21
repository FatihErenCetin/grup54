"""Scope-drift deterministik backtest kapısı (#31).

Yanlış alarm ürünün güvenini aşındırdığı için birincil metrik alert precision:
beklenen `in_scope` iken `drift/non_goal_violation` üretmek FP sayılır.
Üç-sınıf accuracy ayrıca non-goal ile genel drift ayrımını korur.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ensemble.engine.scope import ScopeService
from ensemble.integrations.gemini.scope_judge import FakeScopeJudgeAdapter

DEFAULT_CORPUS = Path(__file__).parent / "datasets" / "scope-corpus.json"
MIN_TOTAL = 18
# 18 vakalık korpusta tek in_scope yanlış alarmı bile 10/11=0.9091'e düşürür.
MIN_ALERT_PRECISION = 0.95
MIN_ACCURACY = 0.80


@dataclass(frozen=True)
class ScopeEvalReport:
    total: int
    correct: int
    tp: int
    fp: int
    fn: int
    predictions: tuple[tuple[str, str, str], ...]

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def alert_precision(self) -> float:
        denominator = self.tp + self.fp
        return self.tp / denominator if denominator else 0.0

    @property
    def alert_recall(self) -> float:
        denominator = self.tp + self.fn
        return self.tp / denominator if denominator else 0.0


class _CorpusHarness:
    def __init__(self, scope: dict[str, Any], case: dict[str, Any]) -> None:
        self.scope = scope
        self.case = case

    def read_scope(self, sprint: str) -> dict[str, Any]:
        if sprint != "3":
            raise KeyError(sprint)
        return self.scope

    def read_tasks(self) -> list[dict[str, Any]]:
        return [
            {
                "task_id": "T-31",
                "title": self.case["title"],
                "body": self.case["body"],
                "paths": self.case["paths"],
            }
        ]

    def read_active(self) -> list[dict[str, Any]]:
        return []


def run_scope_eval(path: Path = DEFAULT_CORPUS) -> ScopeEvalReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scope = payload["scope"]
    predictions: list[tuple[str, str, str]] = []
    correct = tp = fp = fn = 0

    for case in payload["cases"]:
        service = ScopeService(
            _CorpusHarness(scope, case),
            FakeScopeJudgeAdapter(),
            sprint="3",
        )
        actual = service.check_scope("T-31").verdict
        expected = case["expected"]
        predictions.append((case["id"], expected, actual))
        correct += actual == expected

        expected_alert = expected != "in_scope"
        actual_alert = actual != "in_scope"
        if expected_alert and actual_alert:
            tp += 1
        elif not expected_alert and actual_alert:
            fp += 1
        elif expected_alert and not actual_alert:
            fn += 1

    return ScopeEvalReport(
        total=len(predictions),
        correct=correct,
        tp=tp,
        fp=fp,
        fn=fn,
        predictions=tuple(predictions),
    )


def evaluate_scope_gate(report: ScopeEvalReport) -> list[str]:
    violations: list[str] = []
    if report.total < MIN_TOTAL:
        violations.append(f"toplam vaka {report.total} < {MIN_TOTAL}")
    if report.alert_precision < MIN_ALERT_PRECISION:
        violations.append(
            f"alert precision {report.alert_precision:.4f} < {MIN_ALERT_PRECISION:.2f}"
        )
    if report.accuracy < MIN_ACCURACY:
        violations.append(f"accuracy {report.accuracy:.4f} < {MIN_ACCURACY:.2f}")
    return violations


def main() -> None:
    report = run_scope_eval()
    violations = evaluate_scope_gate(report)
    print("Scope-drift eval (#31)")
    print(
        f"total={report.total} accuracy={report.accuracy:.4f} "
        f"alert_precision={report.alert_precision:.4f} "
        f"alert_recall={report.alert_recall:.4f} FP={report.fp}"
    )
    for case_id, expected, actual in report.predictions:
        marker = "OK" if expected == actual else "MISS"
        print(f"{marker:4} {case_id}: expected={expected} actual={actual}")
    if violations:
        print("KIRILDI: " + "; ".join(violations))
        sys.exit(1)
    print("GECTI - scope false-positive kapisi yesil.")


if __name__ == "__main__":
    main()
