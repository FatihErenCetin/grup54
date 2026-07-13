from fastapi import APIRouter

from ensemble.api.deps import BoardServiceDep
from ensemble.api.schemas import BoardResponse

router = APIRouter(prefix="/board", tags=["board"])


@router.get("")
def get_board(board_service: BoardServiceDep) -> BoardResponse:
    return BoardResponse(cards=board_service.get_cards())
