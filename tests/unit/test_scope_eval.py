from dataclasses import replace

from eval.scope_eval import evaluate_scope_gate, run_scope_eval


def test_scope_eval_korpusu_false_positive_kapisini_gecer():
    report = run_scope_eval()

    assert report.total >= 18
    assert report.fp == 0
    assert report.alert_precision == 1.0
    assert evaluate_scope_gate(report) == []


def test_scope_eval_kapisi_tek_false_positive_i_bile_reddeder():
    report = run_scope_eval()
    one_false_positive = replace(report, fp=1)

    assert any("alert precision" in item for item in evaluate_scope_gate(one_false_positive))
