from typing import Callable

from sqlalchemy.orm import Session

from ensemble.models import BoardCard
from ensemble.store.models import TaskProjectionRow


class BoardService:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def get_cards(self) -> list[BoardCard]:
        with self.session_factory() as session:
            rows = session.query(TaskProjectionRow).all()
            return [row.to_board_card() for row in rows]
