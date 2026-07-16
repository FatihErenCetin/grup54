"""Threshold sweep (#29) unit testleri."""

from eval.sweep import run_sweep


def test_sweep_produces_correct_number_of_points():
    """Sweep toplam kombinasyon sayısı doğru olmalı."""
    jg = [0.0, 0.1]
    sg = [0.0, 0.2]
    report = run_sweep(
        jaccard_grid=jg,
        similarity_grid=sg,
        include_same_author_axis=True,
    )
    # 2 jaccard × 2 similarity × 2 same_author = 8
    assert len(report.points) == 8


def test_sweep_without_same_author_axis():
    """Aynı-yazar ekseni kapatılınca kombinasyon yarıya iner."""
    jg = [0.0, 0.1]
    sg = [0.0, 0.2]
    report = run_sweep(
        jaccard_grid=jg,
        similarity_grid=sg,
        include_same_author_axis=False,
    )
    # 2 × 2 × 1 = 4
    assert len(report.points) == 4
    assert all(not p.exclude_same_author for p in report.points)


def test_sweep_finds_best_f1():
    """Sweep en iyi F1 noktasını bulmalı."""
    report = run_sweep(
        jaccard_grid=[0.0, 0.1],
        similarity_grid=[0.0, 0.3],
        include_same_author_axis=False,
    )
    assert report.best is not None
    # En iyi F1, tüm noktaların F1'inden küçük veya eşit olmamalı
    for p in report.points:
        if not p.exclude_same_author:
            assert report.best.f1 >= p.f1 or (
                report.best.f1 == p.f1 and report.best.precision >= p.precision
            )


def test_sweep_report_to_dict_is_json_serializable():
    """Sweep raporu JSON'a dönüştürülebilir olmalı."""
    import json

    report = run_sweep(
        jaccard_grid=[0.0],
        similarity_grid=[0.0],
        include_same_author_axis=False,
    )
    d = report.to_dict()
    s = json.dumps(d)
    parsed = json.loads(s)
    assert "best" in parsed
    assert "grid" in parsed
    assert parsed["total_combinations"] == 1


def test_sweep_all_points_have_valid_metrics():
    """Tüm sweep noktalarının metrikleri 0-1 aralığında olmalı."""
    report = run_sweep(
        jaccard_grid=[0.0, 0.1],
        similarity_grid=[0.0, 0.2],
        include_same_author_axis=False,
    )
    for p in report.points:
        assert 0.0 <= p.precision <= 1.0, f"precision={p.precision}"
        assert 0.0 <= p.recall <= 1.0, f"recall={p.recall}"
        assert 0.0 <= p.f1 <= 1.0, f"f1={p.f1}"
        assert p.tp >= 0
        assert p.fp >= 0
        assert p.fn >= 0
        assert p.tn >= 0
        assert p.total == p.tp + p.fp + p.fn + p.tn


def test_sweep_best_excluding_same_author_exists():
    """Aynı-yazar ekseni açıkken best_excluding_same dolu olmalı."""
    report = run_sweep(
        jaccard_grid=[0.0],
        similarity_grid=[0.0],
        include_same_author_axis=True,
    )
    assert report.best is not None
    assert report.best_excluding_same is not None
    assert not report.best.exclude_same_author
    assert report.best_excluding_same.exclude_same_author


def test_sweep_excluding_same_has_fewer_cases():
    """Aynı-yazar hariç sweep'te daha az vaka olmalı."""
    report = run_sweep(
        jaccard_grid=[0.0],
        similarity_grid=[0.0],
        include_same_author_axis=True,
    )
    assert report.best is not None
    assert report.best_excluding_same is not None
    assert report.best_excluding_same.total < report.best.total
