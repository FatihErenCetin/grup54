from ensemble.models import ScopeVerdict
from ensemble.ports import JudgePort
from ensemble_shared.harness import HarnessPort


class ScopeService:
    def __init__(self, harness_port: HarnessPort, judge_port: JudgePort):
        self.harness_port = harness_port
        self.judge_port = judge_port

    def check_scope(self, ref: str) -> ScopeVerdict:
        # TODO: Implement scope-drift logic (Issue #31)
        raise NotImplementedError("Scope check not implemented yet")
