from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from threading import Lock

from ensemble.engine.cache import KeyedLockRegistry, TtlLruCache
from ensemble.ports import EmbeddingsPort


DEFAULT_EMBEDDING_DIMENSIONS = 768
DEFAULT_EMBEDDING_CACHE_MAX_ENTRIES = 2048

# `TtlLruCache` pozitif (sonlu) `max_entries` zorunlu kılar - `CachedEmbeddings`
# ise açıkça `max_entries=None` verildiğinde "sınırsız" kullanımı destekler.
# Bu sentinel, "sınırsız"ı TtlLruCache'in
# sözleşmesine uyan pratikte-asla-ulaşılamayacak dev bir üst sınıra çevirir -
# TtlLruCache'in KENDİSİNİ (üç judge sarmalayıcısının da paylaştığı ortak
# kod) "None = sınırsız" özel-durumuyla kirletmemek için (#63 takip).
_UNBOUNDED_MAX_ENTRIES = 2**62


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

    Varsayılan kapasite 2048 girdidir; böylece local/dev süreci de uzun ömürlü
    kullanımda sınırsız büyümez. Hosted demo modunda (#63) daha sıkı
    `DEMO_CACHE_MAX_ENTRIES` değeri wiring katmanından verilir. Bilinçli olarak
    sınırsız kullanım gereken özel çağrılar açıkça `max_entries=None` geçebilir.

    **#63 takip (ikinci tur) — el yazması `OrderedDict` yerine `engine/cache.py`
    ortak alt yapısı:** eski uygulama `get(key)`/`move_to_end(key)`'i KİLİTSİZ
    yapıyordu; eş zamanlı bir tahliye (`popitem`) aynı anahtarı silerse
    `move_to_end` `KeyError` fırlatıyordu (bkz. `TtlLruCache` docstring'i +
    `test_embeddings_cache_es_zamanlilikta_keyerror_vermez`). Depo artık
    `TtlLruCache` (kilitli `get`/`set`) — `_cache` özel alanı YOK, yerine
    `self.cache` (bkz. `_CachedJudgeBase.cache` ile aynı isimlendirme).

    **Tekil-uçuş (single-flight), batch semantiği KORUNARAK:** `embed()` bir
    METIN LISTESI alır ve eksikleri TEK bir `inner.embed()` çağrısında
    toplu gönderir (fatura optimizasyonu - farklı metinleri ayrı ayrı
    sorgulamaz). `TtlLruCache.get_or_compute()` TEK anahtar için tasarlandığı
    için burada DOĞRUDAN kullanılmıyor; onun yerine AYNI iki birincil şeyi
    (`KeyedLockRegistry` + `TtlLruCache.get`/`_peek`/`set`) kullanan, ÇOK
    anahtarlı kendi tekil-uçuş turunu (`_fill_misses`) yürütür: eksik
    anahtarların kilitleri DETERMİNİSTİK (sıralı) sırada alınır (çapraz
    kilitlenme/deadlock önlenir - iki farklı çağrı kesişen anahtar
    kümeleriyle gelse bile), kilit altında double-check yapılır (başka bir
    thread bu arada doldurmuş olabilir), yalnız HÂLÂ eksik kalanlar TEK bir
    `inner.embed()` çağrısında hesaplanır. Aynı metnin N eş zamanlı isteği
    → `inner.embed()` TAM 1 KEZ çağrılır (bkz.
    `test_embeddings_cache_ayni_metin_es_zamanli_inner_bir_kez_cagrilir`).

    **Kopya disiplini:** değerler `list[float]` yani MUTABLE. Cache'e
    YAZARKEN (`self.cache.set`) ve OKURKEN (çağırana dönüşte) her zaman bir
    KOPYA kullanılır - çağıran döndürülen listeyi yerinde mutasyona uğratırsa
    (`vector[0] = 0.0` gibi) cache'in kendi kopyası ASLA kirlenmez (bkz.
    `test_embeddings_cache_donen_vektor_mutasyona_kapali`). Bu KOPYA iki AYRI
    yerde uygulanır - okuma (HIT hızlı-yolu `embed()` satır ~135 VE MISS
    dönüşü `_fill_misses` sonu) ile yazma (`_fill_misses` içi
    `stored = list(vector)`) birbirinden BAĞIMSIZDIR; biri kaldırılsa bile
    diğeri testi YEŞİL tutabileceği için ayrı ayrı kilitlenmiştir (bkz.
    `test_embeddings_cache_hit_yolundan_donen_vektor_mutasyona_kapali` +
    `test_embeddings_cache_yazma_tarafi_kopyasi_izole`).

    **Kilit defteri temizliği (#63 sertleştirme turu):** `_fill_misses`'in
    edinme döngüsü yarıda kesilirse (ör. bir kilit `.acquire()` istisna
    fırlatırsa) `finally`, YALNIZ gerçekten kayıt defterine YAZILMIŞ
    anahtarları (`registered_keys`) serbest bırakır - `unique_miss_keys`'in
    TAMAMINI DEĞİL. Aksi halde hiç kaydedilmemiş bir anahtar için
    `self._locks.release()` çağırmak `KeyError` fırlatıp orijinal istisnayı
    MASKELER (bkz.
    `test_embeddings_cache_fill_misses_kilit_edinmede_istisna_orijinali_maskelemez`) -
    `cache.py::TtlLruCache.get_or_compute`'daki AYNI disiplin.
    """

    def __init__(
        self,
        inner: EmbeddingsPort,
        key_fn: Callable[[str, str], str] = content_hash,
        *,
        max_entries: int | None = DEFAULT_EMBEDDING_CACHE_MAX_ENTRIES,
        ttl_s: float = float("inf"),
        single_flight_wait_s: float | None = None,
        time_fn: Callable[[], float] = time.monotonic,
    ):
        if max_entries is not None and max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.inner = inner
        self.key_fn = key_fn
        # Açıkça None verilmesi, geriye uyumlu sınırsız kullanım kaçışıdır.
        self.max_entries = max_entries
        effective_max_entries = (
            max_entries if max_entries is not None else _UNBOUNDED_MAX_ENTRIES
        )
        self.cache = TtlLruCache(
            ttl_s=ttl_s,
            max_entries=effective_max_entries,
            time_fn=time_fn,
            single_flight_wait_s=single_flight_wait_s,
        )
        # Judge sarmalayıcılarındaki `_locks`'un (cache.py) eşdeğeri - burada
        # ÇOK anahtarlı bir batch üzerinde çalıştığı için `TtlLruCache`'in
        # KENDİ `_locks`'undan (tekil-anahtar `get_or_compute` içindir) AYRI
        # kendi kayıt defterini tutar.
        self._locks = KeyedLockRegistry()
        # `TtlLruCache` kurucusunun çözdüğü NİHAİ değeri geri okuyoruz - tek
        # doğruluk kaynağı `TtlLruCache` olsun diye (burada AYRICA hesaplama
        # yapılmaz, modül sabitiyle senkron kalır).
        self._single_flight_wait_s = self.cache.single_flight_wait_s

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        keys = [self.key_fn(text, task_type) for text in texts]
        result_by_position: list[list[float] | None] = [None] * len(texts)
        miss_positions: list[int] = []

        for index, key in enumerate(keys):
            cached = self.cache.get(key)
            if cached is not None:
                result_by_position[index] = list(cached)  # okurken KOPYA
            else:
                miss_positions.append(index)

        if miss_positions:
            self._fill_misses(texts, task_type, keys, miss_positions, result_by_position)

        return [vector for vector in result_by_position if vector is not None]

    def _fill_misses(
        self,
        texts: list[str],
        task_type: str,
        keys: list[str],
        miss_positions: list[int],
        result_by_position: list[list[float] | None],
    ) -> None:
        # Deterministik (alfabetik) sıra: iki farklı `embed()` çağrısı
        # kesişen eksik anahtar kümeleriyle eş zamanlı gelse bile, HERKES
        # kilitleri AYNI global sırada alır - çapraz bekleme (deadlock)
        # oluşamaz (klasik "sıralı kaynak edinme" garantisi).
        unique_miss_keys = sorted({keys[i] for i in miss_positions})
        # `registered_keys`, `self._locks.acquire(key)` GERÇEKTEN başarıyla
        # çağrılmış (kayıt defterine yazılmış) anahtarları tutar -
        # `unique_miss_keys`'İN KENDİSİNİ DEĞİL. Edinme döngüsü yarıda
        # kesilirse (ör. `lock.acquire(timeout=...)` istisna fırlatırsa),
        # kalan anahtarlar kayıt defterine HİÇ YAZILMAMIŞTIR - `finally`
        # bunlar için `release()` çağırırsa `KeyedLockRegistry.release()`
        # `KeyError` fırlatır ve ORİJİNAL istisnayı MASKELER (bkz.
        # `test_embeddings_cache_fill_misses_kilit_edinmede_istisna_orijinali_maskelemez`).
        # `cache.py::get_or_compute`'daki AYNI disiplin burada da uygulanır.
        registered_keys: list[str] = []
        held_locks: list[tuple[str, Lock]] = []
        try:
            for key in unique_miss_keys:
                lock = self._locks.acquire(key)
                registered_keys.append(key)
                if lock.acquire(timeout=self._single_flight_wait_s):
                    held_locks.append((key, lock))
                # Zaman aşımında kilitsiz devam edilir - `TtlLruCache.
                # get_or_compute`'daki "zarif düşüş" ile aynı felsefe (bkz.
                # cache.py docstring'i): bu anahtar aşağıda yine de
                # hesaplanacak, yalnız nadiren başka bir thread'le
                # çakışabilir - sonsuza dek bloklanmaktan iyidir.

            resolved: dict[str, list[float]] = {}
            still_missing_keys: list[str] = []
            still_missing_texts: list[str] = []
            for key in unique_miss_keys:
                # Sayaç ARTIRMAYAN double-check (`_peek`) - bu thread kilidi
                # beklerken başka bir thread zaten hesaplayıp yazmış olabilir.
                cached = self.cache.peek(key)
                if cached is not None:
                    resolved[key] = list(cached)
                else:
                    still_missing_keys.append(key)
                    # Batch içinde AYNI metin birden fazla pozisyonda
                    # geçebilir - inner.embed()'e YALNIZ İLK metni gönderiyoruz
                    # (anahtar zaten içerik-hash'i, hangi pozisyondan geldiği
                    # önemsiz).
                    first_index = next(i for i in miss_positions if keys[i] == key)
                    still_missing_texts.append(texts[first_index])

            if still_missing_texts:
                embedded = self.inner.embed(still_missing_texts, task_type)
                if len(embedded) != len(still_missing_texts):
                    raise ValueError(
                        "inner embeddings must return the same number of vectors as texts"
                    )
                for key, vector in zip(still_missing_keys, embedded):
                    stored = list(vector)  # yazarken KOPYA
                    self.cache.set(key, stored)
                    resolved[key] = stored

            for index in miss_positions:
                result_by_position[index] = list(resolved[keys[index]])  # okurken KOPYA
        finally:
            for key, lock in held_locks:
                lock.release()
            for key in registered_keys:
                self._locks.release(key)
