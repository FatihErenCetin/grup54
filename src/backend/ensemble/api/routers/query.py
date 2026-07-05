from fastapi import APIRouter

router = APIRouter(prefix="/query", tags=["query"])


@router.get("")
def ask_project(q: str) -> dict:
    # TODO: Implement NL query over project state
    return {"answer": "Not implemented yet", "citations": []}
