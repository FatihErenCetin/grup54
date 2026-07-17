from datetime import datetime, timezone

from ensemble.engine.radar import (
    SEMANTIC_SIMILARITY_TASK,
    RadarService,
    file_overlap_candidates,
    jaccard_similarity,
    semantic_hunk_candidates,
    semantic_hunk_similarity,
)
from ensemble.models import Detection, NormalizedEvent


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


class StaticGitHub:
    def __init__(
        self,
        events: list[NormalizedEvent],
        backfill_events: list[NormalizedEvent] | None = None,
        compare_files: dict[tuple[str, str], list[str]] | None = None,
        failing_compare: set[tuple[str, str]] | None = None,
    ):
        self.events = events
        self.backfill_events = backfill_events
        self.compare_files = compare_files or {}
        self.failing_compare = failing_compare or set()
        self.since_calls: list[datetime] = []
        self.backfill_calls: list[int] = []
        self.compare_calls: list[tuple[str, str]] = []

    def fetch_events(self, since: datetime) -> list[NormalizedEvent]:
        self.since_calls.append(since)
        return self.events

    def fetch_backfill_events(self, limit_per_type: int = 50) -> list[NormalizedEvent]:
        self.backfill_calls.append(limit_per_type)
        return self.backfill_events if self.backfill_events is not None else self.events

    def compare(self, base: str, head: str) -> list[str]:
        self.compare_calls.append((base, head))
        if (base, head) in self.failing_compare:
            raise RuntimeError("compare failed")
        return self.compare_files.get((base, head), [])


class DedupingGitHub:
    def __init__(self, events: list[NormalizedEvent]):
        self.events = events
        self.seen_ids: set[str] = set()
        self.since_calls: list[datetime] = []
        self.backfill_calls: list[int] = []

    def fetch_events(self, since: datetime) -> list[NormalizedEvent]:
        self.since_calls.append(since)
        fresh = [event for event in self.events if event.id not in self.seen_ids]
        self.seen_ids.update(event.id for event in fresh)
        return fresh

    def fetch_backfill_events(self, limit_per_type: int = 50) -> list[NormalizedEvent]:
        self.backfill_calls.append(limit_per_type)
        selected = self.events[:limit_per_type]
        fresh = [event for event in selected if event.id not in self.seen_ids]
        self.seen_ids.update(event.id for event in fresh)
        return fresh

    def compare(self, base: str, head: str) -> list[str]:
        return []


class RecordingJudge:
    def __init__(self, severity: str = "high", confidence: float = 0.9):
        self.severity = severity
        self.confidence = confidence
        self.calls: list[tuple[NormalizedEvent, NormalizedEvent, list[str], float]] = []

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float
    ) -> Detection:
        self.calls.append((a, b, overlap, sim))
        return Detection(
            id=f"{a.id}-{b.id}",
            actors=sorted({a.actor, b.actor}),
            branches=sorted({x for x in (a.branch, b.branch) if x}),
            files=sorted(overlap),
            severity=self.severity,
            confidence=self.confidence,
            rationale="recorded",
        )


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


def test_radar_service_judges_semantic_overlap_candidates():
    first = event("a", "semih", ["src/radar.py"])
    second = event("b", "enes", ["src/radar.py"])
    judge = RecordingJudge(severity="high", confidence=0.95)
    service = RadarService(
        github_port=StaticGitHub([first, second]),
        judge_port=judge,
        embeddings_port=KeywordEmbeddings(),
        diffs_by_event={
            "a": {"src/radar.py": "@@ -1 +1 @@\n-old\n+same intent"},
            "b": {"src/radar.py": "@@ -1 +1 @@\n-old\n+same intent"},
        },
        window_days=100_000,
    )

    detections = service.get_detections()

    assert len(detections) == 1
    assert detections[0].id == "a-b"
    assert detections[0].files == ["src/radar.py"]
    assert len(judge.calls) == 1
    assert judge.calls[0][2] == ["src/radar.py"]
    assert judge.calls[0][3] == 1.0


def test_radar_service_uses_backfill_on_first_call_then_polling():
    backfill_first = event("backfill-a", "semih", ["src/radar.py"])
    backfill_second = event("backfill-b", "enes", ["src/radar.py"])
    polling_first = event("poll-a", "semih", ["src/other.py"])
    polling_second = event("poll-b", "enes", ["src/other.py"])
    github = StaticGitHub(
        [polling_first, polling_second],
        backfill_events=[backfill_first, backfill_second],
    )
    service = RadarService(
        github_port=github,
        judge_port=RecordingJudge(),
        embeddings_port=KeywordEmbeddings(),
        window_days=100_000,
        backfill_limit=7,
    )

    first = service.get_detections()
    second = service.get_detections()

    assert github.backfill_calls == [7]
    assert len(github.since_calls) == 1
    assert first[0].id == "backfill-a-backfill-b"
    assert [detection.id for detection in second] == [
        "backfill-a-backfill-b",
        "poll-a-poll-b",
    ]


def test_radar_service_keeps_backfill_detections_when_adapter_dedups_seen_events():
    first = event("backfill-a", "semih", ["src/radar.py"])
    second = event("backfill-b", "enes", ["src/radar.py"])
    github = DedupingGitHub([first, second])
    service = RadarService(
        github_port=github,
        judge_port=RecordingJudge(),
        embeddings_port=KeywordEmbeddings(),
        window_days=100_000,
        backfill_limit=50,
    )

    first_poll = service.get_detections()
    second_poll = service.get_detections()
    third_poll = service.get_detections()

    assert github.backfill_calls == [50]
    assert len(github.since_calls) == 2
    assert [detection.id for detection in first_poll] == ["backfill-a-backfill-b"]
    assert [detection.id for detection in second_poll] == ["backfill-a-backfill-b"]
    assert [detection.id for detection in third_poll] == ["backfill-a-backfill-b"]


def test_radar_service_can_disable_backfill():
    first = event("a", "semih", ["src/radar.py"])
    second = event("b", "enes", ["src/radar.py"])
    github = StaticGitHub([first, second])
    service = RadarService(
        github_port=github,
        judge_port=RecordingJudge(),
        embeddings_port=KeywordEmbeddings(),
        window_days=100_000,
        backfill_limit=0,
    )

    detections = service.get_detections()

    assert github.backfill_calls == []
    assert len(github.since_calls) == 1
    assert len(detections) == 1


def test_radar_service_includes_low_severity_by_default():
    first = event("a", "semih", ["src/radar.py"])
    second = event("b", "enes", ["src/radar.py"])
    judge = RecordingJudge(severity="low", confidence=0.2)
    service = RadarService(
        github_port=StaticGitHub([first, second]),
        judge_port=judge,
        embeddings_port=KeywordEmbeddings(),
        diffs_by_event={
            "a": {"src/radar.py": "@@ -1 +1 @@\n-old\n+same intent"},
            "b": {"src/radar.py": "@@ -1 +1 @@\n-old\n+same intent"},
        },
        window_days=100_000,
    )

    detections = service.get_detections()

    assert len(detections) == 1
    assert detections[0].severity == "low"
    assert len(judge.calls) == 1


def test_radar_service_can_filter_low_severity_when_requested():
    first = event("a", "semih", ["src/radar.py"])
    second = event("b", "enes", ["src/radar.py"])
    judge = RecordingJudge(severity="low", confidence=0.2)
    service = RadarService(
        github_port=StaticGitHub([first, second]),
        judge_port=judge,
        embeddings_port=KeywordEmbeddings(),
        diffs_by_event={
            "a": {"src/radar.py": "@@ -1 +1 @@\n-old\n+same intent"},
            "b": {"src/radar.py": "@@ -1 +1 @@\n-old\n+same intent"},
        },
        include_low_severity=False,
        window_days=100_000,
    )

    assert service.get_detections() == []
    assert len(judge.calls) == 1


def test_radar_service_respects_min_similarity_before_judge():
    first = event("a", "semih", ["src/radar.py"])
    second = event("b", "enes", ["src/radar.py"])
    judge = RecordingJudge()
    service = RadarService(
        github_port=StaticGitHub([first, second]),
        judge_port=judge,
        embeddings_port=KeywordEmbeddings(),
        diffs_by_event={
            "a": {"src/radar.py": "@@ -1 +1 @@\n-old\n+same intent"},
            "b": {"src/radar.py": "@@ -1 +1 @@\n-old\n+different intent"},
        },
        min_similarity=0.1,
        window_days=100_000,
    )

    assert service.get_detections() == []
    assert judge.calls == []


def test_radar_service_uses_compare_for_branch_events_without_files():
    first = event("a", "semih", [])
    second = event("b", "enes", ["src/radar.py"])
    github = StaticGitHub(
        [first, second],
        compare_files={("main", "T-a"): ["src/radar.py"]},
    )
    judge = RecordingJudge(severity="med", confidence=0.7)
    service = RadarService(
        github_port=github,
        judge_port=judge,
        embeddings_port=KeywordEmbeddings(),
        diffs_by_event={
            "a": {"src/radar.py": "@@ -1 +1 @@\n-old\n+same intent"},
            "b": {"src/radar.py": "@@ -1 +1 @@\n-old\n+same intent"},
        },
        window_days=100_000,
    )

    detections = service.get_detections()

    assert github.compare_calls == [("main", "T-a")]
    assert len(detections) == 1
    assert detections[0].files == ["src/radar.py"]


def test_radar_service_memoizes_compare_for_same_branch():
    first = event("a", "semih", [])
    second = event("b", "enes", ["src/radar.py"])
    third = event("c", "fatih", [])
    third = third.model_copy(update={"branch": "T-a"})
    github = StaticGitHub(
        [first, second, third],
        compare_files={("main", "T-a"): ["src/radar.py"]},
    )
    service = RadarService(
        github_port=github,
        judge_port=RecordingJudge(),
        embeddings_port=KeywordEmbeddings(),
        window_days=100_000,
    )

    service.get_detections()

    assert github.compare_calls == [("main", "T-a")]


def test_radar_service_keeps_radar_up_when_compare_fails():
    first = event("a", "semih", [])
    second = event("b", "enes", ["src/radar.py"])
    github = StaticGitHub(
        [first, second],
        failing_compare={("main", "T-a")},
    )
    judge = RecordingJudge()
    service = RadarService(
        github_port=github,
        judge_port=judge,
        embeddings_port=KeywordEmbeddings(),
        window_days=100_000,
    )

    assert service.get_detections() == []
    assert github.compare_calls == [("main", "T-a")]
    assert judge.calls == []
