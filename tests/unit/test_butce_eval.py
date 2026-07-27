"""Eval çağrı-sayısı bütçesi (#256) testleri.

`eval/gate.py` (precision-gate, #30) testlerinin (`test_eval_gate.py`) maliyet
ikizi: saf `evaluate_budget_gate` sınır testleri + fixture'a karşı GERÇEK
`RadarService.collect()` çağrısı (`test_real_fixture_passes_budget_gate`).

Sonuncusu bu PR'ın asıl kırmızı-veren testi: `radar.py`'deki dosya-kesişimi
filtresi (`if not overlap: continue`) kaldırılırsa aday sayısı C(n,2)'ye
fırlar, judge çağrısı 5'ten 45'e çıkar ve bu test KIRILIR (doğrulama: bu
satırı geçici olarak silip `make test` koşarak yapıldı, ardından geri
alındı - regresyonu SESSİZCE geçirmediğini kanıtlamak için).
"""

from eval.butce_eval import (
    MAX_EMBED_CALLS,
    MAX_GITHUB_CALLS,
    MAX_JUDGE_CALLS,
    BudgetReport,
    evaluate_budget_gate,
    run_budget_gate,
)


def _report(*, judge: int = 5, embed: int = 5, github: int = 11, events: int = 10) -> BudgetReport:
    return BudgetReport(events=events, judge_calls=judge, embed_calls=embed, github_calls=github)


def test_gate_passes_at_observed_counts():
    assert evaluate_budget_gate(_report()) == []


def test_gate_boundary_is_inclusive():
    """Tam bütçede (`<=`) geçer; bir fazlasında kırılır."""
    assert evaluate_budget_gate(
        _report(judge=MAX_JUDGE_CALLS, embed=MAX_EMBED_CALLS, github=MAX_GITHUB_CALLS)
    ) == []
    assert evaluate_budget_gate(_report(judge=MAX_JUDGE_CALLS + 1)) != []
    assert evaluate_budget_gate(_report(embed=MAX_EMBED_CALLS + 1)) != []
    assert evaluate_budget_gate(_report(github=MAX_GITHUB_CALLS + 1)) != []


def test_gate_fails_on_judge_call_explosion():
    """#255'in canlıda gördüğü şey: judge çağrısı bütçeyi patlatır."""
    violations = evaluate_budget_gate(_report(judge=45))
    assert any("judge" in v for v in violations)


def test_gate_fails_on_embed_call_explosion():
    violations = evaluate_budget_gate(_report(embed=200))
    assert any("embed" in v for v in violations)


def test_gate_fails_on_github_call_explosion():
    violations = evaluate_budget_gate(_report(github=500))
    assert any("GitHub" in v for v in violations)


def test_report_line_matches_kabul_kriteri_4():
    """Kabul kriteri #4: 'bu korpuste bir /radar = X judge · Y embed · Z GitHub çağrısı'."""
    line = _report().as_line()
    assert "judge" in line
    assert "embed" in line
    assert "GitHub çağrısı" in line


def test_real_fixture_passes_budget_gate():
    """Asıl iş: sabit fixture üzerinde GERÇEK `RadarService.collect()` yolu.

    Bu test kırmızıysa maliyet regresyonu var demektir (CI de aynı
    `make eval-butce` ile kırmızı olur). Sayılar `RadarService`'e enjekte
    edilen sayaçlı port'lardan gelir - `file_overlap_candidates`,
    `semantic_hunk_candidates`, `_judge_all` gibi alt-adımlar DEĞİL,
    `collect()`'in tam yolu ölçülür (#162 pipeline-parite dersi).
    """
    report = run_budget_gate()
    violations = evaluate_budget_gate(report)

    assert violations == [], (
        f"Bütçe kırıldı: judge={report.judge_calls} embed={report.embed_calls} "
        f"github={report.github_calls} — {violations}"
    )
    # Gözlenen tam değerler (fixture: 10 olay, 5 dosya-kesişim çifti) — bu
    # sabitler kayarsa (ör. fixture değişti) bilerek güncellenmeli, kazara
    # DEĞİL: mutasyon testinin gücü tam bu daralıktan gelir.
    assert report.events == 10
    assert report.judge_calls == 5
    assert report.embed_calls == 5
    assert report.github_calls == 11
