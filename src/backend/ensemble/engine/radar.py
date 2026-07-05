from ensemble.models import Detection
from ensemble.ports import GitHubPort, JudgePort


class RadarService:
    def __init__(self, github_port: GitHubPort, judge_port: JudgePort):
        self.github_port = github_port
        self.judge_port = judge_port

    def get_detections(self) -> list[Detection]:
        # TODO: Implement conflict radar logic (Issue #17)
        return []
