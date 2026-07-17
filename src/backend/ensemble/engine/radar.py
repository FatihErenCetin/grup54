from dataclasses import dataclass
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from itertools import combinations

from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import EmbeddingsPort, GitHubPort, JudgePort
from ensemble.engine.chunking import chunk_diff
from ensemble.engine.embeddings import HashEmbeddings
from ensemble.engine.vectorstore import cosine_similarity


SEMANTIC_SIMILARITY_TASK = "SEMANTIC_SIMILARITY"
DEFAULT_RADAR_WINDOW_DAYS = 14


@dataclass(frozen=True)
class FileOverlapCandidate:
    a: NormalizedEvent
    b: NormalizedEvent
    overlap: list[str]
    jaccard: float


@dataclass(frozen=True)
class SemanticHunkCandidate:
    a: NormalizedEvent
    b: NormalizedEvent
    overlap: list[str]
    jaccard: float
    similarity: float
    path_scores: dict[str, float]


def jaccard_similarity(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def file_overlap_candidates(
    events: list[NormalizedEvent], min_jaccard: float = 0.0
) -> list[FileOverlapCandidate]:
    candidates: list[FileOverlapCandidate] = []

    for a, b in combinations(events, 2):
        if a.actor == b.actor:
            continue

        overlap = sorted(set(a.files) & set(b.files))
        if not overlap:
            continue

        score = jaccard_similarity(a.files, b.files)
        if score < min_jaccard:
            continue

        a, b = _canonical_pair(a, b)
        candidates.append(
            FileOverlapCandidate(a=a, b=b, overlap=overlap, jaccard=score)
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate.jaccard,
            candidate.a.ts,
            candidate.b.ts,
            candidate.a.id,
            candidate.b.id,
        ),
    )


def semantic_hunk_candidates(
    candidates: list[FileOverlapCandidate],
    diffs_by_event: Mapping[str, Mapping[str, str]],
    embeddings: EmbeddingsPort,
    min_similarity: float = 0.0,
) -> list[SemanticHunkCandidate]:
    semantic_candidates: list[SemanticHunkCandidate] = []

    for candidate in candidates:
        path_scores: dict[str, float] = {}
        for path in candidate.overlap:
            left_diff = diffs_by_event.get(candidate.a.id, {}).get(path, "")
            right_diff = diffs_by_event.get(candidate.b.id, {}).get(path, "")
            path_scores[path] = semantic_hunk_similarity(
                left_diff,
                right_diff,
                path=path,
                embeddings=embeddings,
            )

        # TODO(#163): 0.0 burada "diff hunk yok, sim bilinmiyor" anlamina da
        # geliyor. JudgePort sim: float | None kontrati HAZIR (Ek C, PR #161);
        # bilinmiyor'u dusuk benzerlikten ayirma isi #163'te, eval delta'siyla.
        similarity = max(path_scores.values(), default=0.0)
        if similarity < min_similarity:
            continue

        semantic_candidates.append(
            SemanticHunkCandidate(
                a=candidate.a,
                b=candidate.b,
                overlap=candidate.overlap,
                jaccard=candidate.jaccard,
                similarity=similarity,
                path_scores=path_scores,
            )
        )

    return sorted(
        semantic_candidates,
        key=lambda candidate: (
            -candidate.similarity,
            -candidate.jaccard,
            candidate.a.ts,
            candidate.b.ts,
            candidate.a.id,
            candidate.b.id,
        ),
    )


def semantic_hunk_similarity(
    left_diff: str,
    right_diff: str,
    path: str,
    embeddings: EmbeddingsPort,
) -> float:
    left_chunks = chunk_diff(left_diff, path=path)
    right_chunks = chunk_diff(right_diff, path=path)
    if not left_chunks or not right_chunks:
        return 0.0

    left_texts = [chunk.text for chunk in left_chunks]
    right_texts = [chunk.text for chunk in right_chunks]
    vectors = embeddings.embed(left_texts + right_texts, SEMANTIC_SIMILARITY_TASK)
    if len(vectors) != len(left_texts) + len(right_texts):
        raise ValueError("embeddings must return one vector per hunk")

    left_vectors = vectors[: len(left_texts)]
    right_vectors = vectors[len(left_texts) :]
    return max(
        cosine_similarity(left, right)
        for left in left_vectors
        for right in right_vectors
    )


def _canonical_pair(
    a: NormalizedEvent, b: NormalizedEvent
) -> tuple[NormalizedEvent, NormalizedEvent]:
    if _event_order_key(a) <= _event_order_key(b):
        return a, b
    return b, a


def _event_order_key(event: NormalizedEvent) -> tuple[str, str, str, str]:
    return (
        event.id,
        event.actor,
        event.branch or "",
        event.ref,
    )


class RadarService:
    def __init__(
        self,
        github_port: GitHubPort,
        judge_port: JudgePort,
        embeddings_port: EmbeddingsPort | None = None,
        diffs_by_event: Mapping[str, Mapping[str, str]] | None = None,
        window_days: int = DEFAULT_RADAR_WINDOW_DAYS,
        min_jaccard: float = 0.0,
        min_similarity: float = 0.0,
        include_low_severity: bool = True,
        default_base: str = "main",
    ):
        if window_days <= 0:
            raise ValueError("window_days must be positive")
        self.github_port = github_port
        self.judge_port = judge_port
        self.embeddings_port = embeddings_port or HashEmbeddings()
        self.diffs_by_event = diffs_by_event or {}
        self.window_days = window_days
        self.min_jaccard = min_jaccard
        self.min_similarity = min_similarity
        self.include_low_severity = include_low_severity
        self.default_base = default_base
        self._compare_cache: dict[tuple[str, str], list[str]] = {}

    def get_detections(self) -> list[Detection]:
        events = self._events_with_compare_files(self.github_port.fetch_events(self._since()))
        file_candidates = file_overlap_candidates(events, min_jaccard=self.min_jaccard)
        semantic_candidates = semantic_hunk_candidates(
            file_candidates,
            self.diffs_by_event,
            self.embeddings_port,
            min_similarity=self.min_similarity,
        )

        detections = [
            self.judge_port.judge_conflict(
                candidate.a,
                candidate.b,
                candidate.overlap,
                candidate.similarity,
            )
            for candidate in semantic_candidates
        ]
        if not self.include_low_severity:
            detections = [
                detection
                for detection in detections
                if detection.severity in {"med", "high"}
            ]

        return sorted(
            detections,
            key=lambda detection: (
                _severity_rank(detection.severity),
                -detection.confidence,
                detection.id,
            ),
        )

    def _since(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=self.window_days)

    def _events_with_compare_files(
        self, events: list[NormalizedEvent]
    ) -> list[NormalizedEvent]:
        enriched: list[NormalizedEvent] = []
        for event in events:
            if event.files or not event.branch:
                enriched.append(event)
                continue

            key = (self.default_base, event.branch)
            if key not in self._compare_cache:
                try:
                    self._compare_cache[key] = self.github_port.compare(*key)
                except Exception:
                    self._compare_cache[key] = []
            files = self._compare_cache[key]
            enriched.append(event.model_copy(update={"files": files}))
        return enriched


def _severity_rank(severity: str) -> int:
    return {"high": 0, "med": 1, "low": 2}.get(severity, 3)
