"""Hosted demo cached-verdict katmanı (#63) — pahalı AI çağrılarının (Gemini
judge) sonucunu deterministik bir içerik-hash anahtarıyla önbelleğe alır.

Yalnız `DEMO_MODE=true` iken app.py tarafından judge port'ların ÜSTÜNE sarılır
(bkz. app.py). Sarmalayıcılar mevcut `JudgePort`/`QueryJudgePort`/`ScopeJudgePort`
Protocol'lerini AYNEN uygular — port imzası değişmez, `integrations/gemini/*`
hiç değişmez.

En büyük fatura kaynağı: frontend Radar sayfasını ~10 sn'de bir poll'luyor
(`usePolling`) ve `RadarService.get_detections()` her istekte her aday çift
için `judge_port.judge_conflict()` çağırıyor (memoizasyon yoktu) — tek açık
sekme dakikada 6 kez tüm çiftleri Gemini'ye yeniden sorduruyordu. Bu modülün
asıl hedefi budur.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from threading import Lock
from typing import Any

from ensemble.models import (
    Detection,
    NormalizedEvent,
    QueryDocument,
    QueryJudgement,
    ScopeCandidate,
    ScopeJudgement,
)
from ensemble.ports import JudgePort, QueryJudgePort, ScopeJudgePort


def _digest(payload: Any) -> str:
    """`embeddings.py::content_hash` ile aynı felsefe: sort_keys'li JSON dump
    üzerinden sha256 — anahtar KİMLİK değil İÇERİK (aynı içerikli farklı nesne
    örnekleri aynı anahtara düşer)."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class TtlLruCache:
    """Saf TTL + LRU-boyut-sınırlı önbellek. `time_fn` enjekte edilebilir
    (testte `sleep` yok); `hits`/`misses` sayaçları eval/gözlem içindir."""

    def __init__(
        self,
        ttl_s: float,
        max_entries: int,
        *,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl_s = float(ttl_s)
        self._max_entries = max_entries
        self._time_fn = time_fn
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires_at, value = entry
            if expires_at <= self._time_fn():
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (self._time_fn() + self._ttl_s, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)  # en eski (LRU) girdiyi tahliye et

    def __len__(self) -> int:
        return len(self._data)


class CachedConflictJudge:
    """`JudgePort` sarmalayıcısı — RadarService'in her poll'da aynı çifti
    yeniden yargılamasını önler (bkz. modül docstring'i)."""

    def __init__(
        self,
        inner: JudgePort,
        *,
        ttl_s: float,
        max_entries: int,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.inner = inner
        self.cache = TtlLruCache(ttl_s, max_entries, time_fn=time_fn)

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection:
        key = _digest(
            {
                "a": a.model_dump(mode="json"),
                "b": b.model_dump(mode="json"),
                "overlap": sorted(overlap),
                "sim": sim,
            }
        )
        cached = self.cache.get(key)
        if cached is not None:
            return cached.model_copy(deep=True)
        result = self.inner.judge_conflict(a, b, overlap, sim)
        self.cache.set(key, result.model_copy(deep=True))
        return result


class CachedQueryJudge:
    """`QueryJudgePort` sarmalayıcısı — Ask'ın tekrar sorulan sorularını
    Gemini'ye yeniden göndermez."""

    def __init__(
        self,
        inner: QueryJudgePort,
        *,
        ttl_s: float,
        max_entries: int,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.inner = inner
        self.cache = TtlLruCache(ttl_s, max_entries, time_fn=time_fn)

    def answer_query(self, question: str, documents: list[QueryDocument]) -> QueryJudgement:
        key = _digest(
            {
                "question": question,
                "documents": [document.model_dump(mode="json") for document in documents],
            }
        )
        cached = self.cache.get(key)
        if cached is not None:
            return cached.model_copy(deep=True)
        result = self.inner.answer_query(question, documents)
        self.cache.set(key, result.model_copy(deep=True))
        return result


class CachedScopeJudge:
    """`ScopeJudgePort` sarmalayıcısı — aynı ref+subject+aday üçlüsünü
    tekrar yargılamaz."""

    def __init__(
        self,
        inner: ScopeJudgePort,
        *,
        ttl_s: float,
        max_entries: int,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.inner = inner
        self.cache = TtlLruCache(ttl_s, max_entries, time_fn=time_fn)

    def judge_scope(
        self, ref: str, subject: str, candidates: list[ScopeCandidate]
    ) -> ScopeJudgement:
        key = _digest(
            {
                "ref": ref,
                "subject": subject,
                "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            }
        )
        cached = self.cache.get(key)
        if cached is not None:
            return cached.model_copy(deep=True)
        result = self.inner.judge_scope(ref, subject, candidates)
        self.cache.set(key, result.model_copy(deep=True))
        return result
