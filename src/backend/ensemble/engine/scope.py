from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from pydantic import ValidationError

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
from ensemble.models import (
    ScopeCandidate,
    ScopeCurrent,
    ScopeItemRef,
    ScopeJudgement,
    ScopeVerdict,
    Signals,
)
from ensemble.ports import EmbeddingsPort, ScopeJudgePort, ScopeSubjectPort
from ensemble_shared.harness import HarnessError, HarnessPort

DEFAULT_SCOPE_SPRINT = "3"
DEFAULT_VERDICT_HISTORY_LIMIT = 100


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
        verdict_history_limit: int = DEFAULT_VERDICT_HISTORY_LIMIT,
    ):
        if not sprint:
            raise ValueError("sprint must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if verdict_history_limit <= 0:
            raise ValueError("verdict_history_limit must be positive")
        self.harness_port = harness_port
        self.judge_port = judge_port
        self.embeddings_port = embeddings_port
        self.subject_port = subject_port
        self.sprint = sprint
        self.top_k = top_k
        self._verdicts: deque[ScopeVerdict] = deque(maxlen=verdict_history_limit)
        self._verdicts_lock = Lock()

    def check_scope(self, ref: str) -> ScopeVerdict:
        subject = resolve_scope_subject(
            self.harness_port,
            ref,
            subject_port=self.subject_port,
            default_sprint=self.sprint,
        )
        scope = self._read_scope(subject.sprint or self.sprint)
        candidates = retrieve_scope_candidates(
            subject.text,
            scope_items(scope),
            embeddings_port=self.embeddings_port,
            top_k=self.top_k,
        )

        cheap = cheap_scope_prejudge(subject.text, candidates)
        judgement = cheap or self.judge_port.judge_scope(ref, subject.text, candidates)
        evidence = _evidence_for(judgement, candidates)

        verdict = ScopeVerdict(
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
        with self._verdicts_lock:
            self._verdicts.append(verdict)
        return verdict

    def get_current_scope(self) -> ScopeCurrent:
        scope = self._read_scope(self.sprint)
        if str(scope.get("status") or "").casefold() != "frozen":
            raise ScopeUnavailableError("scope belgesi frozen değil; PO onayı bekleniyor")

        goal = str(scope.get("body") or "").strip()
        in_scope = [str(item).strip() for item in scope.get("goals") or [] if str(item).strip()]
        non_goals = [
            str(item).strip() for item in scope.get("non_goals") or [] if str(item).strip()
        ]
        raw = {
            "goal": goal,
            "in_scope": in_scope,
            "non_goals": non_goals,
            "version": scope.get("version"),
            "frozen_at": scope.get("frozen_at"),
            "ref": scope.get("ref") or scope.get("path"),
            "commit_sha": scope.get("commit_sha"),
        }
        try:
            current = ScopeCurrent.model_validate(raw)
        except ValidationError as exc:
            raise ScopeUnavailableError(
                "frozen scope metadata eksik veya bozuk: version, frozen_at, ref, commit_sha"
            ) from exc
        if not current.goal or not current.in_scope or not current.commit_sha.strip():
            raise ScopeUnavailableError(
                "frozen scope goal, in_scope ve commit_sha alanlarını doldurmalı"
            )
        return current

    def _read_scope(self, sprint: str) -> dict[str, Any]:
        try:
            return self.harness_port.read_scope(sprint)
        except HarnessError as exc:
            raise ScopeUnavailableError(f"sprint-{sprint} scope belgesi kullanılamıyor") from exc

    def list_verdicts(self) -> list[ScopeVerdict]:
        with self._verdicts_lock:
            return list(reversed(self._verdicts))

    def verdict_counts(self) -> dict[str, int]:
        counts = Counter(verdict.verdict for verdict in self.list_verdicts())
        return {
            "in_scope": counts["in_scope"],
            "drift": counts["drift"],
            "non_goal_violation": counts["non_goal_violation"],
        }


def _evidence_for(judgement: ScopeJudgement, candidates: list[ScopeCandidate]) -> ScopeItemRef:
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
