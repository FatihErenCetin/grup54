from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable
from threading import Lock

from ensemble.ports import EmbeddingsPort


DEFAULT_EMBEDDING_DIMENSIONS = 768
DEFAULT_EMBEDDING_CACHE_MAXSIZE = 2048


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
    """Content-hash cache wrapper that preserves EmbeddingsPort's batch API."""

    def __init__(
        self,
        inner: EmbeddingsPort,
        key_fn: Callable[[str, str], str] = content_hash,
        *,
        maxsize: int = DEFAULT_EMBEDDING_CACHE_MAXSIZE,
    ):
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self.inner = inner
        self.key_fn = key_fn
        self.maxsize = maxsize
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_lock = Lock()

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        result_by_position: list[list[float] | None] = [None] * len(texts)
        misses: list[str] = []
        miss_positions: list[int] = []
        miss_keys: list[str] = []

        for index, text in enumerate(texts):
            key = self.key_fn(text, task_type)
            with self._cache_lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
            if cached is None:
                misses.append(text)
                miss_positions.append(index)
                miss_keys.append(key)
            else:
                result_by_position[index] = cached

        if misses:
            embedded = self.inner.embed(misses, task_type)
            if len(embedded) != len(misses):
                raise ValueError("inner embeddings must return the same number of vectors as texts")
            for position, key, vector in zip(miss_positions, miss_keys, embedded):
                with self._cache_lock:
                    self._cache[key] = vector
                    self._cache.move_to_end(key)
                    while len(self._cache) > self.maxsize:
                        self._cache.popitem(last=False)
                result_by_position[position] = vector

        return [vector for vector in result_by_position if vector is not None]
