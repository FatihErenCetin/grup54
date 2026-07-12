from datetime import datetime, timezone

from ensemble.engine.radar import (
    SEMANTIC_SIMILARITY_TASK,
    file_overlap_candidates,
    jaccard_similarity,
    semantic_hunk_candidates,
    semantic_hunk_similarity,
)
from ensemble.models import NormalizedEvent


class KeywordEmbeddings:
    def __init__(self):
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        self.calls.append((tuple(texts), task_type))
        vectors: list[list[float]] = []
        for text in texts:
            if "same intent" in text:
                vectors.append([1.0, 0.0])
            elif "different intent" in text:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([0.5, 0.5])
        return vectors


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


def test_semantic_hunk_similarity_uses_max_hunk_cosine():
    embeddings = KeywordEmbeddings()
    left = "\n".join(
        [
            "@@ -1,2 +1,2 @@",
            "-old unrelated",
            "+new different intent",
            "@@ -10,2 +10,2 @@",
            "-old behavior",
            "+new same intent",
        ]
    )
    right = "\n".join(
        [
            "@@ -5,2 +5,2 @@",
            "-previous behavior",
            "+updated same intent",
        ]
    )

    score = semantic_hunk_similarity(
        left,
        right,
        path="src/backend/ensemble/engine/radar.py",
        embeddings=embeddings,
    )

    assert score == 1.0
    assert embeddings.calls[0][1] == SEMANTIC_SIMILARITY_TASK


def test_semantic_hunk_candidates_score_only_overlap_paths():
    embeddings = KeywordEmbeddings()
    candidates = file_overlap_candidates(
        [
            event("a", "semih", ["src/radar.py", "src/only-a.py"]),
            event("b", "enes", ["src/radar.py", "src/only-b.py"]),
        ]
    )
    diffs_by_event = {
        "a": {
            "src/radar.py": "@@ -1 +1 @@\n-old\n+same intent",
            "src/only-a.py": "@@ -1 +1 @@\n-old\n+different intent",
        },
        "b": {
            "src/radar.py": "@@ -1 +1 @@\n-old\n+same intent",
            "src/only-b.py": "@@ -1 +1 @@\n-old\n+different intent",
        },
    }

    scored = semantic_hunk_candidates(candidates, diffs_by_event, embeddings)

    assert len(scored) == 1
    assert scored[0].similarity == 1.0
    assert scored[0].path_scores == {"src/radar.py": 1.0}


def test_semantic_hunk_candidates_respect_min_similarity():
    embeddings = KeywordEmbeddings()
    candidates = file_overlap_candidates(
        [
            event("a", "semih", ["src/radar.py"]),
            event("b", "enes", ["src/radar.py"]),
        ]
    )
    diffs_by_event = {
        "a": {"src/radar.py": "@@ -1 +1 @@\n-old\n+same intent"},
        "b": {"src/radar.py": "@@ -1 +1 @@\n-old\n+different intent"},
    }

    scored = semantic_hunk_candidates(
        candidates,
        diffs_by_event,
        embeddings,
        min_similarity=0.1,
    )

    assert scored == []


def test_semantic_hunk_candidates_missing_hunks_score_zero():
    embeddings = KeywordEmbeddings()
    candidates = file_overlap_candidates(
        [
            event("a", "semih", ["src/radar.py"]),
            event("b", "enes", ["src/radar.py"]),
        ]
    )

    scored = semantic_hunk_candidates(candidates, {}, embeddings)

    assert scored[0].similarity == 0.0
    assert scored[0].path_scores == {"src/radar.py": 0.0}
