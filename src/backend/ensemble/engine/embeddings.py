from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable

from ensemble.ports import EmbeddingsPort


DEFAULT_EMBEDDING_DIMENSIONS = 768


def content_hash(text: str, task_type: str) -> str:
    payload = f"{task_type}\0{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class HashEmbeddings:
    """Offline EmbeddingsPort implementation for tests and local development."""

    def __init__(self, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        self.calls.append((tuple(texts), task_type))
        return [self._embed_one(text, task_type) for text in texts]

    def _embed_one(self, text: str, task_type: str) -> list[float]:
        seed = content_hash(text, task_type).encode("ascii")
        values: list[float] = []
        counter = 0

        while len(values) < self.dimensions:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            values.extend((byte / 127.5) - 1.0 for byte in digest)
            counter += 1

        return values[: self.dimensions]


class CachedEmbeddings:
    """Content-hash cache wrapper that preserves EmbeddingsPort's batch API.

    `max_entries=None` (varsayılan) = bugünkü sınırsız davranış, sıfır
    regresyon. Hosted demo modda (#63) serbest metin `q` sınırsız cache
    büyütebileceği için (public demo, 512 MB Fly VM) `DEMO_CACHE_MAX_ENTRIES`
    ile bir üst sınır + LRU tahliye devreye sokulur.
    """

    def __init__(
        self,
        inner: EmbeddingsPort,
        key_fn: Callable[[str, str], str] = content_hash,
        *,
        max_entries: int | None = None,
    ):
        if max_entries is not None and max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.inner = inner
        self.key_fn = key_fn
        self.max_entries = max_entries
        self._cache: OrderedDict[str, list[float]] = OrderedDict()

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        result_by_position: list[list[float] | None] = [None] * len(texts)
        misses: list[str] = []
        miss_positions: list[int] = []
        miss_keys: list[str] = []

        for index, text in enumerate(texts):
            key = self.key_fn(text, task_type)
            cached = self._cache.get(key)
            if cached is None:
                misses.append(text)
                miss_positions.append(index)
                miss_keys.append(key)
            else:
                self._cache.move_to_end(key)
                result_by_position[index] = cached

        if misses:
            embedded = self.inner.embed(misses, task_type)
            if len(embedded) != len(misses):
                raise ValueError(
                    "inner embeddings must return the same number of vectors as texts"
                )
            for position, key, vector in zip(miss_positions, miss_keys, embedded):
                self._cache[key] = vector
                self._cache.move_to_end(key)
                result_by_position[position] = vector
                if self.max_entries is not None:
                    while len(self._cache) > self.max_entries:
                        self._cache.popitem(last=False)

        return [vector for vector in result_by_position if vector is not None]
