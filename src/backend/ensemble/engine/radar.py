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
DEFAULT_BACKFILL_LIMIT = 50


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
        backfill_limit: int = DEFAULT_BACKFILL_LIMIT,
        default_base: str = "main",
    ):
        if window_days <= 0:
            raise ValueError("window_days must be positive")
        if backfill_limit < 0:
            raise ValueError("backfill_limit must be non-negative")
        self.github_port = github_port
        self.judge_port = judge_port
        self.embeddings_port = embeddings_port or HashEmbeddings()
        self.diffs_by_event = diffs_by_event or {}
        self.window_days = window_days
        self.min_jaccard = min_jaccard
        self.min_similarity = min_similarity
        self.include_low_severity = include_low_severity
        self.backfill_limit = backfill_limit
        self.default_base = default_base
        self._compare_cache: dict[tuple[str, str], list[str]] = {}
        self._diff_cache: dict[tuple[str, str], dict[str, str]] = {}
        self._known_events: dict[str, NormalizedEvent] = {}
        self._backfill_done = False

    def get_detections(self) -> list[Detection]:
        events = self._current_events()
        file_candidates = file_overlap_candidates(events, min_jaccard=self.min_jaccard)
        diffs = self._diffs_for_candidates(file_candidates)
        semantic_candidates = semantic_hunk_candidates(
            file_candidates,
            diffs,
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

    def _current_events(self) -> list[NormalizedEvent]:
        for event in self._events_with_compare_files(self._fetch_events()):
            self._known_events[event.id] = event

        since = self._since()
        self._known_events = {
            event_id: event
            for event_id, event in self._known_events.items()
            if _datetime_key(event.ts) >= _datetime_key(since)
        }
        return sorted(
            self._known_events.values(),
            key=lambda event: (_datetime_key(event.ts), event.id),
        )

    def _diffs_for_candidates(
        self, candidates: list[FileOverlapCandidate]
    ) -> Mapping[str, Mapping[str, str]]:
        """Semantik hunk aşaması (#23/#152) için path->hunk metni sağlar.

        Constructor'da enjekte edilen `diffs_by_event` ÖNCELİKLİDİR (test-yolu
        korunur, #152 kabul kriteri) - yalnız orada olmayan ve `branch`'i olan
        event'ler için CANLI `github_port.get_diff()` çağrılır (aynı `.compare()`/
        `_compare_cache` deseni: (base, branch) başına bir kez, hata → boş dict,
        radar ayakta kalır).
        """
        diffs: dict[str, Mapping[str, str]] = dict(self.diffs_by_event)
        events = {event.id: event for pair in candidates for event in (pair.a, pair.b)}
        for candidate_event in events.values():
            if candidate_event.id in diffs or not candidate_event.branch:
                continue
            key = (self.default_base, candidate_event.branch)
            if key not in self._diff_cache:
                try:
                    self._diff_cache[key] = self.github_port.get_diff(*key)
                except Exception:
                    self._diff_cache[key] = {}
            diffs[candidate_event.id] = self._diff_cache[key]
        return diffs

    def _fetch_events(self) -> list[NormalizedEvent]:
        if not self._backfill_done:
            self._backfill_done = True
            if self.backfill_limit > 0:
                return self.github_port.fetch_backfill_events(self.backfill_limit)
        return self.github_port.fetch_events(self._since())

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


def _datetime_key(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
