from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class _VectorRecord:
    vec: list[float]
    meta: dict


class InMemoryVectorIndex:
    """VectorIndexPort-compatible local index using cosine similarity."""

    def __init__(self):
        self._records: dict[str, _VectorRecord] = {}

    def upsert(self, id: str, vec: list[float], meta: dict) -> None:
        if not id:
            raise ValueError("id must not be empty")
        if not vec:
            raise ValueError("vec must not be empty")
        self._records[id] = _VectorRecord(vec=vec, meta=dict(meta))

    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]:
        if k <= 0:
            return []
        if not vec:
            raise ValueError("vec must not be empty")

        scored: list[tuple[str, float]] = []
        for id, record in self._records.items():
            scored.append((id, cosine_similarity(vec, record.vec)))
        return sorted(scored, key=lambda item: (-item[1], item[0]))[:k]

    def meta(self, id: str) -> dict:
        return dict(self._records[id].meta)

    def clear(self) -> None:
        self._records.clear()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    return dot / (left_norm * right_norm)
