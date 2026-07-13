from fastapi import APIRouter

from ensemble.api.schemas import QueryResponse

router = APIRouter(prefix="/query", tags=["query"])


@router.get("")
def ask_project(q: str) -> QueryResponse:
    # TODO: Implement NL query over project state
    return QueryResponse(answer="Not implemented yet", citations=[])
