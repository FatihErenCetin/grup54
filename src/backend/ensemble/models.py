from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NormalizedEvent(BaseModel):
    id: str
    type: Literal["commit", "pr", "issue", "branch"]
    actor: str
    branch: str | None
    files: list[str]
    ts: datetime
    ref: str


class Detection(BaseModel):
    id: str
    kind: Literal["conflict"] = "conflict"
    actors: list[str]
    branches: list[str]
    files: list[str]
    severity: Literal["low", "med", "high"]
    confidence: float
    rationale: str


class ScopeVerdict(BaseModel):
    ref: str
    verdict: Literal["in_scope", "drift", "non_goal_violation"]
    confidence: float
    evidence: str


class BoardCard(BaseModel):
    task_id: str
    title: str
    status: Literal["backlog", "todo", "in_progress", "in_review", "done"]
    assignee: str | None
    ref: str | None


class ActorRef(BaseModel):
    """Açık aktör tipi (#32/#52) — kontrat: docs/sprint2-kontratlar.md Ek B1."""

    handle: str
    type: Literal["human", "agent"]
    responsible: str | None = None


class PresenceEntry(BaseModel):
    """.harness/active/* projeksiyonu (#32/#52) — kontrat: Ek B1."""

    actor: ActorRef
    module: str
    task: str | None
    branch: str | None
    since: datetime
