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
