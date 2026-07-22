from datetime import datetime, timezone

from fastapi.testclient import TestClient

from ensemble.api.deps import get_scope_service
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.models import ScopeCurrent, ScopeVerdict


class _ScopeService:
    def __init__(self) -> None:
        self.verdict = ScopeVerdict(
            ref="T-59",
            verdict="in_scope",
            confidence=0.98,
            evidence="IS-1: Scope router",
            judged_at=datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
        )

    def check_scope(self, ref: str) -> ScopeVerdict:
        return self.verdict.model_copy(update={"ref": ref})

    def get_current_scope(self) -> ScopeCurrent:
        return ScopeCurrent(
            goal="Scope bekçisini HTTP yüzüne aç",
            in_scope=["IS-1: Scope router"],
            non_goals=["NG-1: Scope yazma endpoint'i"],
            version="3",
            frozen_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
            ref=".harness/scope/sprint-3.md",
            commit_sha="a" * 40,
        )

    def list_verdicts(self) -> list[ScopeVerdict]:
        return [self.verdict]

    def verdict_counts(self) -> dict[str, int]:
        return {"in_scope": 1, "drift": 0, "non_goal_violation": 0}


def _client() -> TestClient:
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_scope_service] = _ScopeService
    return TestClient(app)


def test_scope_check_gercek_motor_imzasini_httpden_tasir():
    response = _client().get("/scope/check", params={"ref": "PR-42"})

    assert response.status_code == 200
    assert response.json()["ref"] == "PR-42"
    assert response.json()["verdict"] == "in_scope"


def test_scope_current_donmus_snapshot_kontratini_tasir():
    response = _client().get("/scope/current")

    assert response.status_code == 200
    assert response.json()["version"] == "3"
    assert response.json()["commit_sha"] == "a" * 40


def test_scope_verdicts_counts_ve_son_judge_zamanini_tasir():
    response = _client().get("/scope/verdicts")

    assert response.status_code == 200
    assert len(response.json()["verdicts"]) == 1
    assert response.json()["counts"] == {
        "in_scope": 1,
        "drift": 0,
        "non_goal_violation": 0,
    }
    assert response.json()["judged_at"] == "2026-07-21T12:00:00Z"
