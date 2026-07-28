from fastapi import APIRouter

from ensemble.api.deps import TenantBoardServiceDep
from ensemble.api.schemas import BoardResponse

router = APIRouter(prefix="/board", tags=["board"])


@router.get("")
def get_board(board_service: TenantBoardServiceDep) -> BoardResponse:
    # get_cards() DEĞİL get_board() — provenance (last_transition_at/source)
    # için (İş 4, docs/sprint3-kontratlar.md B1 eki). get_cards() imzası/
    # davranışı ayrıca korunuyor, başka çağıranlar etkilenmez.
    board = board_service.get_board()
    return BoardResponse(cards=board.cards, last_transition_at=board.last_transition_at, source=board.source)
