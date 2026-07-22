from fastapi import APIRouter

from ensemble.api.deps import GraphServiceDep
from ensemble.engine.graph import DEFAULT_WINDOW_DAYS
from ensemble.models import TouchGraph

router = APIRouter(tags=["graph"])


@router.get("/graph")
def get_graph(
    graph_service: GraphServiceDep,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> TouchGraph:
    return graph_service.get_graph(window_days=window_days)
