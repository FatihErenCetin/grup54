"""DONE-kapisi eval testi (#24): FakeJudgeAdapter'i #26'nin ground-truth
korpusuna karsi calistirir. Tamamen offline (gercek Gemini yok). Bir dedektor
degisikligi bu tur bir eval delta'si gostermeden 'bitti' sayilmaz (AGENTS.md).
"""

from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from tests.fixtures.conflict_corpus import load_conflict_corpus

_EXPECTED_SEVERITIES = {
    "conflict": {"med", "high"},
    "no_conflict": {"low"},
}


def test_fake_judge_matches_corpus_ground_truth():
    corpus = load_conflict_corpus()
    adapter = FakeJudgeAdapter()

    mismatches = []
    for case in corpus:
        detection = adapter.judge_conflict(case.event_a, case.event_b, case.overlap, case.sim)
        expected = _EXPECTED_SEVERITIES[case.label]
        if detection.severity not in expected:
            mismatches.append((case.case_id, case.label, detection.severity))

    assert not mismatches, f"Korpus uyumsuzluklari (case_id, beklenen_label, gercek_severity): {mismatches}"
