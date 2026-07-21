from __future__ import annotations

from typing import Any

import pytest

from ensemble.engine.scope import (
    SCOPE_RETRIEVAL_TASK,
    ScopeJudgeError,
    ScopeReferenceError,
    ScopeService,
    ScopeUnavailableError,
)
from ensemble.integrations.gemini.scope_judge import FakeScopeJudgeAdapter
from ensemble.models import ScopeCandidate, ScopeJudgement, ScopeSubject


class _Harness:
    def __init__(
        self,
        *,
        tasks: list[dict[str, Any]] | None = None,
        active: list[dict[str, Any]] | None = None,
        scopes: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.tasks = tasks or []
        self.active = active or []
        self.scopes = scopes or {}
        self.read_scope_calls: list[str] = []

    def read_tasks(self) -> list[dict[str, Any]]:
        return self.tasks

    def read_active(self) -> list[dict[str, Any]]:
        return self.active

    def read_scope(self, sprint: str) -> dict[str, Any]:
        self.read_scope_calls.append(sprint)
        return self.scopes[sprint]


class _RecordingJudge:
    def __init__(self, judgement: ScopeJudgement) -> None:
        self.judgement = judgement
        self.calls: list[tuple[str, str, list[ScopeCandidate]]] = []

    def judge_scope(
        self, ref: str, subject: str, candidates: list[ScopeCandidate]
    ) -> ScopeJudgement:
        self.calls.append((ref, subject, candidates))
        return self.judgement


class _Embeddings:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[tuple[list[str], str]] = []

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        self.calls.append((texts, task_type))
        return self.vectors


class _SubjectPort:
    def resolve_scope_subject(self, ref: str) -> ScopeSubject:
        return ScopeSubject(
            ref=ref,
            text="Scope-drift ve çakışma radarını tamamla",
            files=["src/backend/ensemble/engine/scope.py"],
            sprint="3",
        )


def _scope() -> dict[str, Any]:
    return {
        "status": "frozen",
        "body": "G-1: Ekip koordinasyonunu görünür kıl",
        "goals": [
            "IS-1: Scope-drift ve çakışma radarını tamamla",
            "IS-2: Read-only MCP araçlarını yayınla",
        ],
        "non_goals": ["NG-1: Kullanıcı login ve OAuth akışı yazma"],
    }


def _task(**overrides: Any) -> dict[str, Any]:
    task = {
        "task_id": "T-31",
        "title": "Scope-drift ve çakışma radarını tamamla",
        "body": "Kapsam bekçisi motoru",
        "paths": ["src/backend/ensemble/engine/scope.py"],
    }
    task.update(overrides)
    return task


def _service(
    *,
    task: dict[str, Any] | None = None,
    scope: dict[str, Any] | None = None,
    judge: Any | None = None,
    embeddings: Any | None = None,
) -> tuple[ScopeService, _Harness]:
    harness = _Harness(
        tasks=[task or _task()],
        scopes={"3": scope or _scope()},
    )
    service = ScopeService(
        harness,
        judge or FakeScopeJudgeAdapter(),
        embeddings_port=embeddings,
    )
    return service, harness


def test_exact_non_goal_ucuz_gecitte_judge_cagirmadan_ihlal_doner():
    judge = _RecordingJudge(ScopeJudgement(verdict="drift", confidence=0.1))
    service, _ = _service(
        task=_task(title="Kullanıcı login ve OAuth akışı yazma"),
        judge=judge,
    )

    verdict = service.check_scope("T-31")

    assert verdict.verdict == "non_goal_violation"
    assert verdict.confidence == 0.98
    assert verdict.evidence.item_id == "NG-1"
    assert verdict.match_none is False
    assert verdict.signals.matched_text == verdict.evidence.quote
    assert judge.calls == []


def test_exact_in_scope_ucuz_gecitte_in_scope_doner():
    judge = _RecordingJudge(ScopeJudgement(verdict="drift", confidence=0.1))
    service, _ = _service(judge=judge)

    verdict = service.check_scope("T-31-scope-drift")

    assert verdict.verdict == "in_scope"
    assert verdict.evidence.section == "in_scope"
    assert verdict.signals.files == ["src/backend/ensemble/engine/scope.py"]
    assert verdict.judged_at is not None
    assert judge.calls == []


def test_belirsiz_is_judgea_retrieval_adaylariyla_gider():
    judge = _RecordingJudge(
        ScopeJudgement(verdict="in_scope", confidence=0.82, evidence_index=0)
    )
    service, _ = _service(
        task=_task(title="Takım bağlamını ajanlara göster"),
        judge=judge,
    )

    verdict = service.check_scope("T-31")

    assert verdict.verdict == "in_scope"
    assert len(judge.calls) == 1
    assert judge.calls[0][0] == "T-31"
    assert len(judge.calls[0][2]) >= 2


def test_drift_en_yakin_in_scope_kanitini_match_none_ile_tasir():
    judge = _RecordingJudge(ScopeJudgement(verdict="drift", confidence=0.76))
    service, _ = _service(task=_task(title="Mobil oyun skor tablosu"), judge=judge)

    verdict = service.check_scope("T-31")

    assert verdict.verdict == "drift"
    assert verdict.match_none is True
    assert verdict.evidence.section == "in_scope"
    assert verdict.signals.matched_text is None


def test_branch_ref_active_beyanindan_taski_cozer():
    harness = _Harness(
        tasks=[_task()],
        active=[
            {
                "task_id": "T-31",
                "branch": "T-31-scope-drift-dedektoru",
                "intent": "Read-only MCP scope kontrolünü tamamla",
                "paths": ["src/mcp/ensemble_mcp/server.py"],
            }
        ],
        scopes={"3": _scope()},
    )
    service = ScopeService(harness, FakeScopeJudgeAdapter())

    verdict = service.check_scope("T-31-scope-drift-dedektoru")

    assert "src/mcp/ensemble_mcp/server.py" in verdict.signals.files


def test_task_sprint_alani_scope_secimini_override_eder():
    task = _task(sprint="4")
    harness = _Harness(tasks=[task], scopes={"4": _scope()})
    service = ScopeService(harness, FakeScopeJudgeAdapter(), sprint="3")

    service.check_scope("T-31")

    assert harness.read_scope_calls == ["4"]


def test_canli_ref_istege_bagli_subject_port_uzerinden_cozulur():
    harness = _Harness(scopes={"3": _scope()})
    service = ScopeService(
        harness,
        FakeScopeJudgeAdapter(),
        subject_port=_SubjectPort(),
    )

    verdict = service.check_scope("PR-205")

    assert verdict.ref == "PR-205"
    assert verdict.verdict == "in_scope"
    assert verdict.signals.files == ["src/backend/ensemble/engine/scope.py"]


def test_embeddings_verilirse_semantik_retrieval_kullanilir():
    embeddings = _Embeddings(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [0.0, -1.0],
        ]
    )
    judge = _RecordingJudge(
        ScopeJudgement(verdict="in_scope", confidence=0.8, evidence_index=0)
    )
    service, _ = _service(
        task=_task(title="Bilinmeyen ama semantik iş"),
        judge=judge,
        embeddings=embeddings,
    )

    service.check_scope("T-31")

    assert embeddings.calls[0][1] == SCOPE_RETRIEVAL_TASK
    assert judge.calls[0][2][0].similarity == 1.0


def test_eksik_ref_acik_hata_verir():
    harness = _Harness(scopes={"3": _scope()})
    service = ScopeService(harness, FakeScopeJudgeAdapter())

    with pytest.raises(ScopeReferenceError, match="bulunamadı"):
        service.check_scope("PR-999")


def test_taslak_scope_verdict_uretmez():
    scope = _scope()
    scope["status"] = "draft"
    service, _ = _service(scope=scope)

    with pytest.raises(ScopeUnavailableError, match="taslak"):
        service.check_scope("T-31")


def test_judge_non_goal_verdictini_in_scope_kanitina_baglayamaz():
    judge = _RecordingJudge(
        ScopeJudgement(verdict="non_goal_violation", confidence=0.9, evidence_index=0)
    )
    service, _ = _service(task=_task(title="Belirsiz çalışma"), judge=judge)

    with pytest.raises(ScopeJudgeError, match="bağlanamaz"):
        service.check_scope("T-31")


def test_hatalı_embedding_adedi_sessizce_devam_etmez():
    service, _ = _service(embeddings=_Embeddings([[1.0, 0.0]]))

    with pytest.raises(ValueError, match="one vector"):
        service.check_scope("T-31")
