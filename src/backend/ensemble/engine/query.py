from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

from ensemble.models import (
    Citation,
    CitationType,
    NearestRef,
    QueryDocument,
    QueryResult,
    SearchReceipt,
)
from ensemble.ports import EmbeddingsPort, QueryJudgePort, QuerySourcePort, VectorIndexPort

QUERY_DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"
QUERY_EMBEDDING_TASK = "RETRIEVAL_QUERY"
DEFAULT_QUERY_TOP_K = 5
DEFAULT_QUERY_MIN_SEMANTIC_SCORE = 0.5

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_WINDOW_RE = re.compile(r"\bson\s+(\d+)\s*(saat|gün|gun|hafta)\b", re.IGNORECASE)
_CITATION_RE = re.compile(r"\[cite:([^\]\s]+)\]")
_STOP_WORDS = {
    "a",
    "about",
    "and",
    "bir",
    "bu",
    "da",
    "de",
    "ile",
    "için",
    "icin",
    "ne",
    "nedir",
    "olan",
    "olarak",
    "son",
    "the",
    "ve",
}
_CITATION_TYPES: tuple[CitationType, ...] = ("scope", "task", "decision", "event", "pr")


class QueryError(RuntimeError):
    """Ask motorunun kullanıcıya açık hata tabanı."""


class QueryInputError(QueryError):
    """Soru boş ya da değerlendirilemeyecek biçimde."""


class QueryRetrievalError(QueryError):
    """Embedding veya vector-index retrieval tamamlanamadı."""


class QueryJudgeError(QueryError):
    """Judge cevabı kanonik retrieval kanıtına bağlanamadı."""


class QueryService:
    def __init__(
        self,
        source_port: QuerySourcePort,
        embeddings_port: EmbeddingsPort,
        vector_index: VectorIndexPort,
        judge_port: QueryJudgePort,
        *,
        top_k: int = DEFAULT_QUERY_TOP_K,
        min_semantic_score: float = DEFAULT_QUERY_MIN_SEMANTIC_SCORE,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not -1.0 <= min_semantic_score <= 1.0:
            raise ValueError("min_semantic_score must be between -1 and 1")
        self.source_port = source_port
        self.embeddings_port = embeddings_port
        self.vector_index = vector_index
        self.judge_port = judge_port
        self.top_k = top_k
        self.min_semantic_score = min_semantic_score
        self._indexed_hashes: dict[str, str] = {}
        self._index_lock = Lock()

    def ask(self, question: str) -> QueryResult:
        clean_question = question.strip()
        if not clean_question:
            raise QueryInputError("query boş olamaz")

        try:
            corpus = self.source_port.load_query_corpus()
        except Exception as exc:
            raise QueryRetrievalError("proje corpus'u okunamadı") from exc
        now = datetime.now(timezone.utc)
        window, cutoff = _query_window(clean_question, now)
        documents = [
            document
            for document in corpus.documents
            if cutoff is None
            or document.occurred_at is None
            or _as_utc(document.occurred_at) >= cutoff
        ]
        searched = _search_receipts(documents)
        if not documents:
            return _not_found(corpus.last_commit, now, window, searched, [])

        scored = self._retrieve(clean_question, documents)
        nearest = _nearest_refs(scored, self.top_k)
        relevant = [
            item
            for item in scored
            if item.lexical_score > 0.0 or item.semantic_score >= self.min_semantic_score
        ][: self.top_k]
        if not relevant:
            return _not_found(corpus.last_commit, now, window, searched, nearest)

        evidence = [item.document for item in relevant]
        judgement = self.judge_port.answer_query(clean_question, evidence)
        citations = _validated_citations(judgement.answer, judgement.citation_refs, evidence)
        return QueryResult(
            answer=judgement.answer,
            citations=citations,
            as_of=now,
            last_commit=corpus.last_commit,
            window=window,
            confidence=judgement.confidence,
            status="answered",
            searched=searched,
            nearest=nearest,
        )

    def _retrieve(self, question: str, documents: list[QueryDocument]) -> list[_ScoredDocument]:
        by_id = {document.id: document for document in documents}
        try:
            with self._index_lock:
                self._index_documents(documents)
                query_vectors = self.embeddings_port.embed([question], QUERY_EMBEDDING_TASK)
                if len(query_vectors) != 1:
                    raise QueryRetrievalError("query embedding tam olarak bir vektör dönmeli")
                result_limit = max(len(self._indexed_hashes), self.top_k)
                vector_results = self.vector_index.query(query_vectors[0], result_limit)
        except QueryRetrievalError:
            raise
        except Exception as exc:
            raise QueryRetrievalError("vector retrieval tamamlanamadı") from exc

        semantic_by_id = {
            document_id: float(score)
            for document_id, score in vector_results
            if document_id in by_id and math.isfinite(float(score))
        }
        question_tokens = _tokens(question)
        scored = [
            _ScoredDocument(
                document=document,
                semantic_score=semantic_by_id.get(document.id, -1.0),
                lexical_score=_lexical_score(question_tokens, _tokens(document.text)),
            )
            for document in documents
        ]
        return sorted(
            scored,
            key=lambda item: (
                -max(item.semantic_score, item.lexical_score),
                -item.lexical_score,
                -item.semantic_score,
                item.document.id,
            ),
        )

    def _index_documents(self, documents: list[QueryDocument]) -> None:
        changed: list[tuple[QueryDocument, str]] = []
        for document in documents:
            fingerprint = hashlib.sha256(document.text.encode("utf-8")).hexdigest()
            if self._indexed_hashes.get(document.id) != fingerprint:
                changed.append((document, fingerprint))
        if not changed:
            return

        vectors = self.embeddings_port.embed(
            [document.text for document, _fingerprint in changed],
            QUERY_DOCUMENT_TASK,
        )
        if len(vectors) != len(changed):
            raise QueryRetrievalError("document embedding adedi corpus ile eşleşmiyor")
        for (document, fingerprint), vector in zip(changed, vectors):
            self.vector_index.upsert(
                document.id,
                vector,
                {"type": document.type, "ref": document.ref},
            )
            self._indexed_hashes[document.id] = fingerprint


@dataclass(frozen=True)
class _ScoredDocument:
    document: QueryDocument
    semantic_score: float
    lexical_score: float


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _WORD_RE.findall(text.casefold())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _lexical_score(question: set[str], document: set[str]) -> float:
    if not question or not document:
        return 0.0
    return len(question & document) / math.sqrt(len(question) * len(document))


def _query_window(question: str, now: datetime) -> tuple[str | None, datetime | None]:
    match = _WINDOW_RE.search(question)
    if match is None:
        return None, None
    amount = int(match.group(1))
    if amount <= 0:
        return None, None
    unit = match.group(2).casefold()
    if unit == "saat":
        delta = timedelta(hours=amount)
    elif unit in {"gün", "gun"}:
        delta = timedelta(days=amount)
    else:
        delta = timedelta(weeks=amount)
    return match.group(0), now - delta


def _search_receipts(documents: list[QueryDocument]) -> list[SearchReceipt]:
    counts = Counter(document.type for document in documents)
    return [SearchReceipt(type=kind, count=counts[kind]) for kind in _CITATION_TYPES]


def _nearest_refs(scored: list[_ScoredDocument], limit: int) -> list[NearestRef]:
    nearest: list[NearestRef] = []
    seen: set[tuple[str, str]] = set()
    for item in scored:
        key = (item.document.type, item.document.ref)
        if key in seen:
            continue
        seen.add(key)
        nearest.append(NearestRef(type=item.document.type, ref=item.document.ref))
        if len(nearest) >= min(limit, 3):
            break
    return nearest


def _validated_citations(
    answer: str,
    requested_refs: list[str],
    documents: list[QueryDocument],
) -> list[Citation]:
    by_ref = {document.ref: document for document in documents}
    ordered_refs = list(dict.fromkeys(requested_refs))
    if not ordered_refs:
        raise QueryJudgeError("answered cevabı en az bir citation ref gerektirir")
    unknown = [ref for ref in ordered_refs if ref not in by_ref]
    if unknown:
        raise QueryJudgeError("judge retrieval dışında citation ref üretti")
    placeholder_refs = list(dict.fromkeys(_CITATION_RE.findall(answer)))
    if set(placeholder_refs) != set(ordered_refs):
        raise QueryJudgeError("judge citation placeholder'ları bildirdiği ref'lerle eşleşmiyor")

    return [
        Citation(
            type=by_ref[ref].type,
            ref=ref,
            quote=by_ref[ref].quote,
            url=by_ref[ref].url,
            range=by_ref[ref].range,
            n=index,
        )
        for index, ref in enumerate(ordered_refs, start=1)
    ]


def _not_found(
    last_commit: str,
    as_of: datetime,
    window: str | None,
    searched: list[SearchReceipt],
    nearest: list[NearestRef],
) -> QueryResult:
    return QueryResult(
        answer="Bu soru için kanonik proje bağlamında yeterli kanıt bulunamadı.",
        citations=[],
        as_of=as_of,
        last_commit=last_commit,
        window=window,
        confidence="low",
        status="not_found",
        searched=searched,
        nearest=nearest,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
