from __future__ import annotations

import re

from ensemble.engine.scope_context import scope_quote_text
from ensemble.engine.vectorstore import cosine_similarity
from ensemble.models import ScopeCandidate, ScopeItemRef, ScopeJudgement
from ensemble.ports import EmbeddingsPort

SCOPE_RETRIEVAL_TASK = "SEMANTIC_SIMILARITY"
DEFAULT_SCOPE_TOP_K = 4

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_STOP_WORDS = {
    "a", "and", "bir", "bu", "da", "de", "et", "ekle", "ile", "için",
    "kur", "olarak", "or", "sağla", "tamamla", "the", "ve", "veya", "yaz", "yazma",
}


def retrieve_scope_candidates(
    subject: str,
    items: list[ScopeItemRef],
    *,
    embeddings_port: EmbeddingsPort | None,
    top_k: int,
) -> list[ScopeCandidate]:
    lexical = [_lexical_similarity(subject, item.quote) for item in items]
    semantic: list[float] | None = None
    if embeddings_port is not None:
        vectors = embeddings_port.embed(
            [subject, *(item.quote for item in items)],
            SCOPE_RETRIEVAL_TASK,
        )
        if len(vectors) != len(items) + 1:
            raise ValueError("embeddings must return one vector per scope text")
        semantic = [
            (cosine_similarity(vectors[0], vector) + 1.0) / 2.0
            for vector in vectors[1:]
        ]

    scored = [
        ScopeCandidate(
            evidence=item,
            similarity=round(
                max(lexical[index], semantic[index] if semantic is not None else 0.0),
                4,
            ),
        )
        for index, item in enumerate(items)
    ]
    scored.sort(
        key=lambda candidate: (
            -candidate.similarity,
            candidate.evidence.section or "",
            candidate.evidence.item_id or "",
            candidate.evidence.quote,
        )
    )
    selected = scored[:top_k]
    for section in ("in_scope", "non_goals"):
        if not any(candidate.evidence.section == section for candidate in selected):
            best = next(
                (candidate for candidate in scored if candidate.evidence.section == section),
                None,
            )
            if best is not None:
                selected.append(best)
    return selected


def cheap_scope_prejudge(
    subject: str, candidates: list[ScopeCandidate]
) -> ScopeJudgement | None:
    for section, verdict in (
        ("non_goals", "non_goal_violation"),
        ("in_scope", "in_scope"),
    ):
        for index, candidate in enumerate(candidates):
            if candidate.evidence.section == section and _contains_scope_phrase(
                subject, candidate.evidence.quote
            ):
                return ScopeJudgement(
                    verdict=verdict,  # type: ignore[arg-type]
                    confidence=0.98,
                    evidence_index=index,
                )
    return None


def _tokens(text: str) -> set[str]:
    return {
        token
        for match in _WORD_RE.finditer(text)
        if (token := match.group(0).casefold()) not in _STOP_WORDS
    }


def _lexical_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(scope_quote_text(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def _contains_scope_phrase(subject: str, quote: str) -> bool:
    subject_tokens = _tokens(subject)
    quote_tokens = _tokens(scope_quote_text(quote))
    return len(quote_tokens) >= 2 and quote_tokens <= subject_tokens
