from tests.fixtures.conflict_corpus import load_conflict_corpus


def test_corpus_loads_and_not_empty():
    cases = load_conflict_corpus()
    assert len(cases) > 0


def test_case_ids_are_unique():
    cases = load_conflict_corpus()
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids))


def test_labels_are_valid():
    cases = load_conflict_corpus()
    for c in cases:
        assert c.label in ("conflict", "no_conflict")


def test_overlap_is_subset_of_actual_file_intersection():
    cases = load_conflict_corpus()
    for c in cases:
        actual_intersection = set(c.event_a.files) & set(c.event_b.files)
        assert set(c.overlap).issubset(actual_intersection), (
            f"{c.case_id}: overlap {c.overlap} gercek kesisimin {actual_intersection} disina tasiyor"
        )


def test_both_labels_represented():
    cases = load_conflict_corpus()
    labels = {c.label for c in cases}
    assert labels == {"conflict", "no_conflict"}
