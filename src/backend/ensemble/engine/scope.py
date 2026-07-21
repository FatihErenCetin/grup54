from __future__ import annotations

from datetime import datetime, timezone

from ensemble.engine.scope_context import (
    ScopeError as ScopeError,
    ScopeReferenceError as ScopeReferenceError,
    ScopeUnavailableError as ScopeUnavailableError,
    resolve_scope_subject,
    scope_items,
)
from ensemble.engine.scope_retrieval import (
    DEFAULT_SCOPE_TOP_K,
    SCOPE_RETRIEVAL_TASK as SCOPE_RETRIEVAL_TASK,
    cheap_scope_prejudge,
    retrieve_scope_candidates,
)
from ensemble.models import ScopeCandidate, ScopeItemRef, ScopeJudgement, ScopeVerdict, Signals
from ensemble.ports import EmbeddingsPort, ScopeJudgePort, ScopeSubjectPort
from ensemble_shared.harness import HarnessPort

DEFAULT_SCOPE_SPRINT = "3"


class ScopeJudgeError(ScopeError):
    """Judge cevabı kanonik scope kanıtına güvenle bağlanamadı."""


class ScopeService:
    def __init__(
        self,
        harness_port: HarnessPort,
        judge_port: ScopeJudgePort,
        *,
        embeddings_port: EmbeddingsPort | None = None,
        subject_port: ScopeSubjectPort | None = None,
        sprint: str = DEFAULT_SCOPE_SPRINT,
        top_k: int = DEFAULT_SCOPE_TOP_K,
    ):
        if not sprint:
            raise ValueError("sprint must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        self.harness_port = harness_port
        self.judge_port = judge_port
        self.embeddings_port = embeddings_port
        self.subject_port = subject_port
        self.sprint = sprint
        self.top_k = top_k

    def check_scope(self, ref: str) -> ScopeVerdict:
        subject = resolve_scope_subject(
            self.harness_port,
            ref,
            subject_port=self.subject_port,
            default_sprint=self.sprint,
        )
        scope = self.harness_port.read_scope(subject.sprint or self.sprint)
        candidates = retrieve_scope_candidates(
            subject.text,
            scope_items(scope),
            embeddings_port=self.embeddings_port,
            top_k=self.top_k,
        )

        cheap = cheap_scope_prejudge(subject.text, candidates)
        judgement = cheap or self.judge_port.judge_scope(ref, subject.text, candidates)
        evidence = _evidence_for(judgement, candidates)

        return ScopeVerdict(
            ref=ref,
            verdict=judgement.verdict,
            confidence=judgement.confidence,
            evidence=evidence,
            match_none=judgement.verdict == "drift",
            judged_at=datetime.now(timezone.utc),
            signals=Signals(
                files=subject.files,
                matched_text=None if judgement.verdict == "drift" else evidence.quote,
            ),
        )


def _evidence_for(
    judgement: ScopeJudgement, candidates: list[ScopeCandidate]
) -> ScopeItemRef:
    if judgement.evidence_index is None:
        if judgement.verdict != "drift":
            raise ScopeJudgeError("in_scope/non_goal verdict'i kanıt indeksi gerektirir")
        candidate = next(
            (item for item in candidates if item.evidence.section == "in_scope"),
            None,
        )
        if candidate is None:
            raise ScopeJudgeError("drift verdict'i için en yakın in_scope kanıtı bulunamadı")
        return candidate.evidence

    if not 0 <= judgement.evidence_index < len(candidates):
        raise ScopeJudgeError("judge kanıt indeksi retrieval adaylarının dışında")
    evidence = candidates[judgement.evidence_index].evidence
    allowed_sections = {
        "in_scope": {"goal", "in_scope"},
        "non_goal_violation": {"non_goals"},
        "drift": {"goal", "in_scope"},
    }
    if evidence.section not in allowed_sections[judgement.verdict]:
        raise ScopeJudgeError(
            f"{judgement.verdict} verdict'i {evidence.section} kanıtına bağlanamaz"
        )
    return evidence
