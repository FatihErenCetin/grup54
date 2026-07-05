from fastapi import APIRouter

from ensemble.api.deps import BoardServiceDep
from ensemble.models import BoardCard

router = APIRouter(prefix="/board", tags=["board"])


@router.get("")
def get_board(board_service: BoardServiceDep) -> dict:
    cards: list[BoardCard] = board_service.get_cards()
    return {"cards": cards}
