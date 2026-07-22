from fastapi import APIRouter, Query

from ensemble.api.deps import QueryServiceDep
from ensemble.api.errors import ErrorEnvelope
from ensemble.api.schemas import QueryResponse

router = APIRouter(prefix="/query", tags=["query"])


@router.get(
    "",
    responses={400: {"model": ErrorEnvelope, "description": "Geçersiz doğal dil sorgusu"}},
)
def ask_project(
    query_service: QueryServiceDep,
    q: str = Query(min_length=1, max_length=500),
) -> QueryResponse:
    return QueryResponse.model_validate(query_service.ask(q).model_dump())
