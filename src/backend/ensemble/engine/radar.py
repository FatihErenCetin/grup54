from dataclasses import dataclass
from itertools import combinations

from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import GitHubPort, JudgePort


@dataclass(frozen=True)
class FileOverlapCandidate:
    a: NormalizedEvent
    b: NormalizedEvent
    overlap: list[str]
    jaccard: float


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


class RadarService:
    def __init__(self, github_port: GitHubPort, judge_port: JudgePort):
        self.github_port = github_port
        self.judge_port = judge_port

    def get_detections(self) -> list[Detection]:
        # TODO: Implement conflict radar logic (Issue #17)
        return []
