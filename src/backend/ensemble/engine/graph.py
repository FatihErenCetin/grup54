"""Aktör×modül dokunma grafı (#104) — sıfır LLM, saf NormalizedEvent + active/ aggregation.

Kontrat: docs/sprint2-kontratlar.md Ek A (donmuş — #106 ile). Radar ısı matrisi
(#105) + Actors sayfasının (#129) kaynağı.
"""

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ensemble.models import GraphEdge, GraphNode, NormalizedEvent, TouchGraph
from ensemble.store.models import EventRow, PresenceRow

DEFAULT_WINDOW_DAYS = 14


def _module_of(path: str) -> str:
    """Modül adı (kontrat örneği: `src/backend/...` -> `backend`) - hesaplanır,
    şemaya yazılmaz. `src/` jenerik konteyner - ikinci segment asıl modül
    (backend/frontend); başka üst dizinler (docs/, eval/, scripts/...)
    kendi başına anlamlı, ilk segment kullanılır."""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    if parts[0] == "src" and len(parts) > 1:
        return parts[1]
    return parts[0]


def _as_aware_utc(ts: datetime) -> datetime:
    # Ingest normalize + fixture/test verisi karışık naive/aware üretebiliyor
    # (bkz. integrations/github/fake.py) - karşılaştırma öncesi tek tipe çekilir.
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def build_touch_graph(
    events: list[NormalizedEvent],
    active_pairs: set[tuple[str, str]],
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> TouchGraph:
    """Sıfır LLM - saf aggregation. `active_pairs` = {(handle, module), ...}."""
    edge_count: dict[tuple[str, str], int] = defaultdict(int)
    edge_last_ts: dict[tuple[str, str], datetime] = {}
    actor_weight: dict[str, int] = defaultdict(int)
    module_weight: dict[str, int] = defaultdict(int)

    for event in events:
        modules = {_module_of(f) for f in event.files if f}
        for module in modules:
            key = (event.actor, module)
            edge_count[key] += 1
            if key not in edge_last_ts or event.ts > edge_last_ts[key]:
                edge_last_ts[key] = event.ts
            actor_weight[event.actor] += 1
            module_weight[module] += 1

    nodes = [
        GraphNode(id=actor, type="actor", weight=weight)
        for actor, weight in sorted(actor_weight.items())
    ] + [
        GraphNode(id=module, type="module", weight=weight)
        for module, weight in sorted(module_weight.items())
    ]
    edges = [
        GraphEdge(
            actor=actor,
            module=module,
            count=count,
            last_ts=edge_last_ts[(actor, module)],
            is_active_declared=(actor, module) in active_pairs,
        )
        for (actor, module), count in sorted(edge_count.items())
    ]
    return TouchGraph(window_days=window_days, nodes=nodes, edges=edges)


class GraphService:
    """DB projeksiyonundan (#41) TouchGraph üretir - `BoardService` ile aynı DI deseni."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        window_days: int = DEFAULT_WINDOW_DAYS,
    ):
        self.session_factory = session_factory
        self.window_days = window_days

    def get_graph(self, window_days: int | None = None) -> TouchGraph:
        window = window_days if window_days is not None else self.window_days
        since = datetime.now(timezone.utc) - timedelta(days=window)
        with self.session_factory() as session:
            events = [row.to_domain() for row in session.query(EventRow).all()]
            active_pairs = {
                (row.handle, row.module)
                for row in session.query(PresenceRow).all()
                if row.module
            }
        recent = [e for e in events if _as_aware_utc(e.ts) >= since]
        return build_touch_graph(recent, active_pairs, window_days=window)
