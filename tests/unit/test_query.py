from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ensemble.engine.query import QueryJudgeError, QueryRetrievalError, QueryService
from ensemble.engine.vectorstore import InMemoryVectorIndex
from ensemble.models import QueryCorpus, QueryDocument, QueryJudgement


class _Source:
    def __init__(self, documents: list[QueryDocument]) -> None:
        self.corpus = QueryCorpus(documents=documents, last_commit="abc1234")

    def load_query_corpus(self) -> QueryCorpus:
        return self.corpus


class _BrokenSource:
    def load_query_corpus(self) -> QueryCorpus:
        raise RuntimeError("bozuk projection")


class _TokenEmbeddings:
    vocabulary = ("scope", "drift", "postgres", "deploy", "mobil", "oyun")

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        self.calls.append((texts, task_type))
        return [[float(token in text.casefold()) for token in self.vocabulary] for text in texts]


class _Judge:
    def __init__(self, judgement: QueryJudgement | None = None) -> None:
        self.judgement = judgement
        self.calls: list[tuple[str, list[QueryDocument]]] = []

    def answer_query(
        self,
        question: str,
        documents: list[QueryDocument],
    ) -> QueryJudgement:
        self.calls.append((question, documents))
        return self.judgement or QueryJudgement(
            answer=f"Scope-drift sprint kapsamındadır [cite:{documents[0].ref}]",
            citation_refs=[documents[0].ref],
            confidence="high",
        )


def _document(**overrides) -> QueryDocument:
    data = {
        "id": "scope:IS-1",
        "type": "scope",
        "ref": ".harness/scope/sprint-3.md#IS-1",
        "quote": "IS-1: Scope-drift bekçisini tamamla",
        "text": "IS-1: Scope-drift bekçisini tamamla",
    }
    data.update(overrides)
    return QueryDocument.model_validate(data)


def _service(
    documents: list[QueryDocument],
    *,
    judge: _Judge | None = None,
) -> tuple[QueryService, _Judge, _TokenEmbeddings]:
    actual_judge = judge or _Judge()
    embeddings = _TokenEmbeddings()
    return (
        QueryService(
            _Source(documents),
            embeddings,
            InMemoryVectorIndex(),
            actual_judge,
        ),
        actual_judge,
        embeddings,
    )


def test_ilgili_soru_kanonik_citation_ve_tazelik_fisi_doner():
    service, judge, _ = _service([_document()])

    result = service.ask("Scope drift sprintte var mı?")

    assert result.status == "answered"
    assert result.last_commit == "abc1234"
    assert result.confidence == "high"
    assert result.citations[0].ref == ".harness/scope/sprint-3.md#IS-1"
    assert result.citations[0].quote == "IS-1: Scope-drift bekçisini tamamla"
    assert result.citations[0].n == 1
    assert result.searched[0].model_dump() == {"type": "scope", "count": 1}
    assert len(judge.calls) == 1


def test_alakasiz_soru_judge_cagirmadan_durust_red_doner():
    service, judge, _ = _service(
        [
            _document(
                id="task:T-179",
                type="task",
                ref="T-179",
                quote="Postgres sürücüsünü ekle",
                text="Postgres migration ve pgvector sürücüsü",
            )
        ]
    )

    result = service.ask("Mobil oyun skorları nasıl?")

    assert result.status == "not_found"
    assert result.citations == []
    assert result.confidence == "low"
    assert result.nearest[0].ref == "T-179"
    assert judge.calls == []


def test_window_eski_eventi_retrievaldan_cikarir():
    now = datetime.now(timezone.utc)
    recent = _document(
        id="event:recent",
        type="event",
        ref="recent",
        quote="recent",
        text="deploy tamamlandı",
        occurred_at=now - timedelta(hours=2),
    )
    old = _document(
        id="event:old",
        type="event",
        ref="old",
        quote="old",
        text="deploy başladı",
        occurred_at=now - timedelta(days=2),
    )
    service, judge, _ = _service([old, recent])

    result = service.ask("son 24 saat deploy durumu")

    assert result.window == "son 24 saat"
    assert result.status == "answered"
    assert [document.ref for document in judge.calls[0][1]] == ["recent"]
    event_receipt = next(item for item in result.searched if item.type == "event")
    assert event_receipt.count == 1


def test_judge_retrieval_disinda_ref_uyduramaz():
    judge = _Judge(
        QueryJudgement(
            answer="Uydurma cevap [cite:T-999]",
            citation_refs=["T-999"],
            confidence="high",
        )
    )
    service, _, _ = _service([_document()], judge=judge)

    with pytest.raises(QueryJudgeError, match="retrieval dışında"):
        service.ask("Scope drift nedir?")


def test_judge_placeholder_olmadan_citation_veremez():
    ref = ".harness/scope/sprint-3.md#IS-1"
    judge = _Judge(
        QueryJudgement(
            answer="Kaynağı görünmeyen cevap",
            citation_refs=[ref],
            confidence="medium",
        )
    )
    service, _, _ = _service([_document()], judge=judge)

    with pytest.raises(QueryJudgeError, match="placeholder"):
        service.ask("Scope drift nedir?")


def test_judge_cevaba_bildirmedigi_ekstra_placeholder_sokamaz():
    ref = ".harness/scope/sprint-3.md#IS-1"
    judge = _Judge(
        QueryJudgement(
            answer=f"Doğru kaynak [cite:{ref}], gizli kaynak [cite:T-999]",
            citation_refs=[ref],
            confidence="medium",
        )
    )
    service, _, _ = _service([_document()], judge=judge)

    with pytest.raises(QueryJudgeError, match="placeholder"):
        service.ask("Scope drift nedir?")


def test_degisimeyen_corpus_ikinci_soruda_yeniden_indexlenmez():
    service, _, embeddings = _service([_document()])

    service.ask("Scope drift nedir?")
    service.ask("Scope drift var mı?")

    document_calls = [call for call in embeddings.calls if call[1] == "RETRIEVAL_DOCUMENT"]
    query_calls = [call for call in embeddings.calls if call[1] == "RETRIEVAL_QUERY"]
    assert len(document_calls) == 1
    assert len(query_calls) == 2


def test_corpus_okuma_hatasi_not_found_diye_gizlenmez():
    service = QueryService(
        _BrokenSource(),
        _TokenEmbeddings(),
        InMemoryVectorIndex(),
        _Judge(),
    )

    with pytest.raises(QueryRetrievalError, match="corpus'u okunamadı"):
        service.ask("Scope nedir?")
