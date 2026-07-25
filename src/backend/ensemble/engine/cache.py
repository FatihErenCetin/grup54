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

**Single-flight (#63 takip düzeltmesi):** yalın `get()`→miss→`inner.judge_*()`
→`set()` deseni `get` ile `set` ARASINI korumuyordu — aynı anahtar için eş
zamanlı N istek hepsi miss görüp pahalı çağrıyı N KEZ tetikliyordu (public
demoda Gemini faturasının patlamasını önlemenin tüm amacını delen boşluk).
`TtlLruCache.get_or_compute()` anahtar-başına bir kilitle bunu kapatır — bkz.
aşağıdaki `_KeyedLockRegistry` + `get_or_compute` docstring'i.
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

# `get_or_compute` içindeki pahalı `compute()` çağrısı anahtar kilidi ALTINDA
# koşar. `compute()` (örn. Gemini çağrısı) asılırsa aynı anahtarı bekleyen
# diğer istekler sonsuza dek bloklanmasın diye kilit yalnız bu kadar beklenir;
# süre dolunca kilitsiz devam edilir (bkz. `get_or_compute` docstring'i).
_SINGLE_FLIGHT_WAIT_S = 30.0


def _digest(payload: Any) -> str:
    """`embeddings.py::content_hash` ile aynı felsefe: sort_keys'li JSON dump
    üzerinden sha256 — anahtar KİMLİK değil İÇERİK (aynı içerikli farklı nesne
    örnekleri aynı anahtara düşer)."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class _KeyedLockRegistry:
    """Anahtar-başına `Lock` kayıt defteri. Sözlüğün KENDİSİ bir master `Lock`
    ile korunur; bir anahtarın gerçek (uzun sürebilecek) kilitlenmesi bu master
    kilidin DIŞINDA olur — master kilit yalnız kayıt defterini korur, pahalı
    `compute()` çağrısını değil (aksi hâlde tüm anahtarlar birbirini bloklardı).

    Refcount: `acquire()` artırır, `release()` azaltır; son bekleyen çıkınca
    kayıt SİLİNİR — sözlük, geçmişte görülmüş her anahtar için sınırsız
    büyümesin (uzun ömürlü demo süreci)."""

    def __init__(self) -> None:
        self._master = Lock()
        self._entries: dict[str, tuple[Lock, int]] = {}

    def acquire(self, key: str) -> Lock:
        """Anahtarın `Lock`'unu döndürür (yoksa oluşturur) ve refcount'u
        artırır. Çağıran, dönen `Lock` üzerinde KENDİSİ `.acquire()`/`.release()`
        yapar — bu metot yalnız KAYDI yönetir, gerçek kilitlemeyi değil."""
        with self._master:
            lock, refcount = self._entries.get(key, (None, 0))
            if lock is None:
                lock = Lock()
            self._entries[key] = (lock, refcount + 1)
            return lock

    def release(self, key: str) -> None:
        """Refcount'u azaltır; son bekleyen çıkınca kaydı siler (sızıntı yok)."""
        with self._master:
            lock, refcount = self._entries[key]
            if refcount <= 1:
                del self._entries[key]
            else:
                self._entries[key] = (lock, refcount - 1)

    def __len__(self) -> int:
        with self._master:
            return len(self._entries)


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
        self._locks = _KeyedLockRegistry()
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

    def get_or_compute(self, key: str, compute: Callable[[], Any]) -> Any:
        """`get(key)` HIT ise onu döndürür. MISS ise anahtar-başına TEKİL-UÇUŞ
        (single-flight) koruması altında `compute()` çağırır: aynı anahtar için
        eş zamanlı N istek pahalı hesaplamayı YALNIZ 1 KEZ tetikler — kazanan
        hesaplayıp `set()` eder, diğerleri sonucu cache'ten okur. FARKLI
        anahtarlar birbirini bloklamaz (kilit anahtar-başınadır, global değil).

        `compute()` İSTİSNA fırlatırsa hiçbir şey cache'lenmez, kilit bırakılır,
        istisna olduğu gibi çağırana yayılır — sıradaki çağrı yeniden hesaplar.
        Başarısız sonuç ASLA cache'lenmez.

        KİLİTLENME KORUMASI: pahalı `compute()` çağrısı bu kilit ALTINDA koşar.
        `compute()` asılırsa (örn. Gemini çağrısı hiç dönmezse) aynı anahtarı
        bekleyen diğer istekler sonsuza dek bloklanmasın diye kilit yalnız
        `_SINGLE_FLIGHT_WAIT_S` saniye beklenir; süre dolarsa kilit olmadan
        kendi hesabını yapar — bu, tekil-uçuş katmanı eklenmeden ÖNCEKİ
        (racy get/compute/set) davranışa zarif bir düşüştür. İstek thread'ini
        sonsuza kadar bloke etmek, mükerrer bir pahalı çağrıdan daha kötüdür.
        """
        cached = self.get(key)
        if cached is not None:
            return cached

        lock = self._locks.acquire(key)
        acquired = lock.acquire(timeout=_SINGLE_FLIGHT_WAIT_S)
        try:
            if acquired:
                # double-check: bu thread kilidi beklerken başka bir thread
                # zaten hesaplayıp cache'e yazmış olabilir.
                cached = self.get(key)
                if cached is not None:
                    return cached
            # `acquired` False ise (zaman aşımı): kilitsiz devam — yukarıdaki
            # docstring'teki "zarif düşüş".
            value = compute()
            self.set(key, value)
            return value
        finally:
            if acquired:
                lock.release()
            self._locks.release(key)

    def __len__(self) -> int:
        return len(self._data)


class _CachedJudgeBase:
    """Üç port sarmalayıcısının (`CachedConflictJudge`/`CachedQueryJudge`/
    `CachedScopeJudge`) ortak gövdesi: anahtar hesapla → `TtlLruCache.
    get_or_compute()` ile tekil-uçuş koruması altında `inner`'ı çağır → HER
    çağırana kendi derin kopyasını döndür (cache her zaman kendi bağımsız
    derin kopyasını tutar). Alt sınıflar yalnızca kendi port metodunu (anahtar
    + `inner` çağrısı) sağlar — port imzaları (`JudgePort`/`QueryJudgePort`/
    `ScopeJudgePort`) bu sınıfın ALTINDA aynen korunur, bu sınıf hiçbirini
    doğrudan uygulamaz."""

    def __init__(
        self,
        *,
        ttl_s: float,
        max_entries: int,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cache = TtlLruCache(ttl_s, max_entries, time_fn=time_fn)

    def _cached_call(self, key: str, compute: Callable[[], Any]) -> Any:
        def _compute_and_snapshot() -> Any:
            # Cache'e giren değer, `inner`'ın döndürdüğünden BAĞIMSIZ bir
            # derin kopya olsun ki cağıranın sonradan yapacağı mutasyon
            # (bkz. test_hit_donen_nesne_mutasyona_kapali) cache'i etkilemesin.
            return compute().model_copy(deep=True)

        stored = self.cache.get_or_compute(key, _compute_and_snapshot)
        # Depoda tutulan nesneyi DEĞİL, ondan alınan taze bir kopyayı döndür —
        # her çağıran kendi kopyasını alır, hiçbiri cache'in iç nesnesini
        # doğrudan tutmaz.
        return stored.model_copy(deep=True)


class CachedConflictJudge(_CachedJudgeBase):
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
        super().__init__(ttl_s=ttl_s, max_entries=max_entries, time_fn=time_fn)
        self.inner = inner

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
        return self._cached_call(key, lambda: self.inner.judge_conflict(a, b, overlap, sim))


class CachedQueryJudge(_CachedJudgeBase):
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
        super().__init__(ttl_s=ttl_s, max_entries=max_entries, time_fn=time_fn)
        self.inner = inner

    def answer_query(self, question: str, documents: list[QueryDocument]) -> QueryJudgement:
        key = _digest(
            {
                "question": question,
                "documents": [document.model_dump(mode="json") for document in documents],
            }
        )
        return self._cached_call(key, lambda: self.inner.answer_query(question, documents))


class CachedScopeJudge(_CachedJudgeBase):
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
        super().__init__(ttl_s=ttl_s, max_entries=max_entries, time_fn=time_fn)
        self.inner = inner

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
        return self._cached_call(key, lambda: self.inner.judge_scope(ref, subject, candidates))
