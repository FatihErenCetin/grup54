from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ensemble.integrations.query_source import HarnessEventQuerySource
from ensemble.models import NormalizedEvent
from ensemble.store.models import Base, EventRow
from ensemble_shared.harness import HarnessError


class _Harness:
    def read_scope(self, sprint: str) -> dict:
        assert sprint == "3"
        return {
            "path": ".harness/scope/sprint-3.md",
            "body": "G-1: Koordinasyonu görünür kıl",
            "goals": ["IS-1: Scope-drift bekçisini tamamla"],
            "non_goals": ["NG-1: OAuth yazma"],
        }

    def read_tasks(self) -> list[dict]:
        return [
            {
                "task_id": "T-58",
                "title": "Ask endpoint'ini yaz",
                "body": "RAG ve citations",
            }
        ]

    def read_active(self) -> list[dict]:
        return [
            {
                "task_id": "T-58",
                "intent": "QueryService geliştir",
                "module": "engine/query.py",
                "branch": "T-58-query-rag",
            }
        ]


def test_source_harness_ve_eventleri_citation_corpusuna_cevirir(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        session.add(
            EventRow.from_domain(
                NormalizedEvent(
                    id="commit:abc1234",
                    type="commit",
                    actor="semih",
                    branch="T-58-query-rag",
                    files=["src/backend/ensemble/engine/query.py"],
                    ts=datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
                    ref="abc1234",
                )
            )
        )
        session.commit()

    source = HarnessEventQuerySource(
        _Harness(),
        session_factory=sessions,
        repo_root=tmp_path,
        github_owner="FatihErenCetin",
        github_repo="grup54",
    )

    corpus = source.load_query_corpus()

    assert corpus.last_commit == "abc1234"
    assert {document.type for document in corpus.documents} == {"scope", "task", "event"}
    task = next(document for document in corpus.documents if document.ref == "T-58")
    assert "QueryService geliştir" in task.text
    assert task.url.endswith("/issues/58")
    scope = next(document for document in corpus.documents if document.ref.endswith("#IS-1"))
    assert scope.quote == "IS-1: Scope-drift bekçisini tamamla"
    event = next(document for document in corpus.documents if document.id == "commit:abc1234")
    assert event.url.endswith("/commit/abc1234")


class _MissingHarness:
    def read_scope(self, sprint: str) -> dict:
        raise HarnessError(sprint)

    def read_tasks(self) -> list[dict]:
        raise HarnessError("tasks")

    def read_active(self) -> list[dict]:
        raise HarnessError("active")


def test_source_veri_yokken_uydurma_dokuman_uretmez(tmp_path):
    source = HarnessEventQuerySource(_MissingHarness(), repo_root=tmp_path)

    corpus = source.load_query_corpus()

    assert corpus.documents == []
    assert corpus.last_commit == "unavailable"
