from datetime import datetime
from typing import Protocol

from ensemble.models import (
    Detection,
    NormalizedEvent,
    ScopeCandidate,
    ScopeJudgement,
    ScopeSubject,
)

# HarnessPort, shared paketinde (ensemble_shared.harness) yer alıyor ve
# oradan import edilecek. Buraya tekrar yazmıyoruz (GATE 1 kuralı).


class GitHubPort(Protocol):
    def fetch_events(self, since: datetime) -> list[NormalizedEvent]: ...
    def fetch_backfill_events(self, limit_per_type: int = 50) -> list[NormalizedEvent]: ...
    def compare(self, base: str, head: str) -> list[str]: ...


class EmbeddingsPort(Protocol):
    def embed(self, texts: list[str], task_type: str) -> list[list[float]]: ...


class VectorIndexPort(Protocol):
    def upsert(self, id: str, vec: list[float], meta: dict) -> None: ...
    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]: ...


class JudgePort(Protocol):
    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection: ...


class ScopeJudgePort(Protocol):
    def judge_scope(
        self, ref: str, subject: str, candidates: list[ScopeCandidate]
    ) -> ScopeJudgement: ...


class ScopeSubjectPort(Protocol):
    def resolve_scope_subject(self, ref: str) -> ScopeSubject: ...


class ScopeSubjectNotFoundError(LookupError):
    """ScopeSubjectPort verilen ref'i kendi kaynağında çözemedi."""
