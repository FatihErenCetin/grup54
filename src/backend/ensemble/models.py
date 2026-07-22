from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    evidence: "str | ScopeItemRef"
    match_none: bool = False
    judged_at: datetime | None = None
    signals: "Signals | None" = None


class ScopeItemRef(BaseModel):
    quote: str
    item_id: str | None = None
    section: Literal["goal", "in_scope", "non_goals"] | None = None
    line: int | None = None


class Signals(BaseModel):
    files: list[str]
    matched_text: str | None = None


class ScopeCandidate(BaseModel):
    evidence: ScopeItemRef
    similarity: float


class ScopeJudgement(BaseModel):
    verdict: Literal["in_scope", "drift", "non_goal_violation"]
    confidence: float
    evidence_index: int | None = None


class ScopeSubject(BaseModel):
    ref: str
    text: str
    files: list[str] = Field(default_factory=list)
    sprint: str | None = None


class ScopeCurrent(BaseModel):
    goal: str = Field(min_length=1)
    in_scope: list[str] = Field(min_length=1)
    non_goals: list[str]
    version: str = Field(min_length=1)
    frozen_at: datetime
    ref: str = Field(min_length=1)
    commit_sha: str = Field(pattern=r"^[0-9a-fA-F]{7,64}$")


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


class GraphNode(BaseModel):
    """GET /graph düğümü (#104) — kontrat: docs/sprint2-kontratlar.md Ek A."""

    id: str
    type: Literal["actor", "module"]
    weight: int


class GraphEdge(BaseModel):
    """Aktör -> modül kenarı (#104). module = path'in ilk 2 segmenti (HESAPLANIR)."""

    actor: str
    module: str
    count: int
    last_ts: datetime
    is_active_declared: bool


class TouchGraph(BaseModel):
    """GET /graph çıktısı (#104) — sıfır LLM, saf NormalizedEvent + active/ aggregation."""

    window_days: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


CitationType = Literal["scope", "task", "decision", "event", "pr"]


class LineRange(BaseModel):
    start: int = Field(ge=1)
    end: int = Field(ge=1)


class Citation(BaseModel):
    type: CitationType
    ref: str
    quote: str
    url: str | None = None
    range: LineRange | None = None
    n: int | None = Field(default=None, ge=1)


class SearchReceipt(BaseModel):
    type: CitationType
    count: int = Field(ge=0)


class NearestRef(BaseModel):
    type: CitationType
    ref: str


class QueryResult(BaseModel):
    answer: str
    citations: list[str | Citation]
    as_of: datetime
    last_commit: str
    window: str | None = None
    confidence: Literal["low", "medium", "high"]
    status: Literal["answered", "not_found"]
    searched: list[SearchReceipt]
    nearest: list[NearestRef]


class QueryDocument(BaseModel):
    id: str
    type: CitationType
    ref: str
    quote: str
    text: str
    url: str | None = None
    range: LineRange | None = None
    occurred_at: datetime | None = None


class QueryCorpus(BaseModel):
    documents: list[QueryDocument]
    last_commit: str


class QueryJudgement(BaseModel):
    answer: str
    citation_refs: list[str]
    confidence: Literal["low", "medium", "high"]
