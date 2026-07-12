from datetime import datetime, timezone

from ensemble.engine.radar import file_overlap_candidates, jaccard_similarity
from ensemble.models import NormalizedEvent


def event(
    event_id: str,
    actor: str,
    files: list[str],
    ts: datetime | None = None,
) -> NormalizedEvent:
    return NormalizedEvent(
        id=event_id,
        type="commit",
        actor=actor,
        branch=f"T-{event_id}",
        files=files,
        ts=ts or datetime(2026, 7, 9, tzinfo=timezone.utc),
        ref=event_id,
    )


def test_jaccard_similarity_uses_unique_paths():
    score = jaccard_similarity(
        ["src/a.py", "src/a.py", "src/b.py"],
        ["src/a.py", "src/c.py"],
    )

    assert score == 1 / 3


def test_jaccard_similarity_empty_union_is_zero():
    assert jaccard_similarity([], []) == 0.0


def test_file_overlap_candidates_skip_same_actor_and_no_overlap():
    candidates = file_overlap_candidates(
        [
            event("a", "semih", ["src/radar.py", "README.md"]),
            event("b", "semih", ["src/radar.py"]),
            event("c", "enes", ["docs/notes.md"]),
        ]
    )

    assert candidates == []


def test_file_overlap_candidates_return_overlap_and_score():
    candidates = file_overlap_candidates(
        [
            event("a", "semih", ["src/radar.py", "src/models.py"]),
            event("b", "enes", ["src/radar.py", "tests/test_radar.py"]),
        ]
    )

    assert len(candidates) == 1
    assert candidates[0].overlap == ["src/radar.py"]
    assert candidates[0].jaccard == 1 / 3
    assert candidates[0].a.id == "a"
    assert candidates[0].b.id == "b"


def test_file_overlap_candidate_pair_identity_is_input_order_independent():
    first = event("a", "semih", ["src/radar.py"])
    second = event("b", "enes", ["src/radar.py"])

    forward = file_overlap_candidates([first, second])
    reverse = file_overlap_candidates([second, first])

    assert [(candidate.a.id, candidate.b.id) for candidate in forward] == [
        ("a", "b")
    ]
    assert [(candidate.a.id, candidate.b.id) for candidate in reverse] == [
        ("a", "b")
    ]


def test_file_overlap_candidates_respect_min_jaccard():
    candidates = file_overlap_candidates(
        [
            event("a", "semih", ["src/radar.py", "src/models.py"]),
            event("b", "enes", ["src/radar.py", "tests/test_radar.py"]),
        ],
        min_jaccard=0.5,
    )

    assert candidates == []


def test_file_overlap_candidates_are_deterministically_sorted():
    candidates = file_overlap_candidates(
        [
            event("a", "semih", ["src/radar.py", "src/models.py"]),
            event("b", "enes", ["src/radar.py", "src/models.py"]),
            event("c", "fatih", ["src/radar.py", "docs/notes.md"]),
        ]
    )

    assert [(candidate.a.id, candidate.b.id) for candidate in candidates] == [
        ("a", "b"),
        ("a", "c"),
        ("b", "c"),
    ]
