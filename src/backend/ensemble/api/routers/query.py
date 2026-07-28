from fastapi import APIRouter, Query

from ensemble.api.deps import TenantQueryServiceDep
from ensemble.api.errors import ErrorEnvelope
from ensemble.api.schemas import QueryResponse, QueryScanResponse

router = APIRouter(prefix="/query", tags=["query"])


@router.get(
    "",
    responses={400: {"model": ErrorEnvelope, "description": "Geçersiz doğal dil sorgusu"}},
)
def ask_project(
    query_service: TenantQueryServiceDep,
    q: str = Query(min_length=1, max_length=500),
) -> QueryResponse:
    return QueryResponse.model_validate(query_service.ask(q).model_dump())


@router.get("/scan")
def scan_project(query_service: TenantQueryServiceDep) -> QueryScanResponse:
    """#319 — AskPage'in "Tarandı" şeridi. `q` YOK: LLM'e gitmez, yalnız
    corpus'u sayar (bkz. `QueryService.scan` docstring'i)."""
    return QueryScanResponse.model_validate(query_service.scan().model_dump())
