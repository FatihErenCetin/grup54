from ensemble.models import BoardCard
from ensemble_shared.harness import HarnessPort


class BoardService:
    def __init__(self, harness_port: HarnessPort):
        self.harness_port = harness_port

    def get_cards(self) -> list[BoardCard]:
        # TODO: Implement board state projector
        return []
